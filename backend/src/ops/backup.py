"""Database backups (018-app-cloud-deployment, FR-025, FR-026, FR-031, FR-044;
data-model.md §6, research.md R9, contracts/ops-cli.md).

`select_deletions` is the pure retention rule; `run_backup` is the `ops backup` command.
"""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.logging_config import get_logger
from src.ops import alerts
from src.ops.backup_store import BackupStore, make_backup_id
from src.ops.db import OpsError, alembic_revision, connect, libpq, row_counts, run_tool

logger = get_logger("cloud_pricing.ops.backup")

INCOMPLETE_GRACE = timedelta(hours=24)


@dataclass(frozen=True)
class BackupRecord:
    id: str
    created_at: datetime
    verified: bool


def parse_backup_time(backup_id: str) -> datetime:
    """The UTC time at the start of a backup id."""
    return datetime.strptime(backup_id.split("-", 1)[0], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def select_deletions(backups: list[BackupRecord], *, keep: int, now: datetime) -> list[str]:
    """Ids to delete, oldest last: verified backups beyond the newest `keep`, and unverified
    (incomplete) ones older than 24 hours. The newest verified backup is never in the list
    (FR-026). Decides only; deletes nothing."""
    newest_first = sorted(backups, key=lambda b: b.created_at, reverse=True)
    verified = [b for b in newest_first if b.verified]
    keep_ids = {b.id for b in verified[: max(keep, 1)]}
    deletions = []
    for backup in newest_first:
        if backup.id in keep_ids:
            continue
        if backup.verified or now - backup.created_at > INCOMPLETE_GRACE:
            deletions.append(backup.id)
    return deletions


# --- The `backup` command -----------------------------------------------------------------------


def _records(store: BackupStore) -> list[BackupRecord]:
    records = [
        BackupRecord(id=m["id"], created_at=parse_backup_time(m["id"]),
                     verified=m.get("verified") is True)
        for m in store.list_backups()
    ]
    # A dump without metadata is an unfinished upload: incomplete, never verified.
    records += [
        BackupRecord(id=i, created_at=parse_backup_time(i), verified=False)
        for i in store.list_orphan_dumps()
    ]
    return records


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run_backup(
    kind: str,
    *,
    database_url: str,
    store: BackupStore,
    keep: int,
    release: str,
    environment: str,
    now: datetime | None = None,
) -> dict:
    """Dump, check, upload, re-read and verify one backup, then apply retention.

    Row counts and the dump come from the same exported snapshot, so the counts describe
    exactly what is in the dump. Any failure alerts and raises `OpsError(4)`; nothing is
    deleted unless the new backup is verified.
    """
    now = now or datetime.now(UTC)
    backup_id = make_backup_id(kind, release, now)
    try:
        with tempfile.TemporaryDirectory(prefix="cp-backup-") as tmp:
            dump = Path(tmp) / f"{backup_id}.dump"
            url, env = libpq(database_url)
            # autocommit, so this BEGIN really starts the transaction (psycopg would otherwise
            # have opened a READ COMMITTED one already) and the counts share the dump's snapshot.
            with connect(database_url, autocommit=True) as conn:
                conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
                isolation = conn.execute("SHOW transaction_isolation").fetchone()[0]
                if isolation != "repeatable read":
                    raise OpsError(1, f"backup transaction is {isolation}, not repeatable read")
                snapshot = conn.execute("SELECT pg_export_snapshot()").fetchone()[0]
                counts = row_counts(conn)
                revision = alembic_revision(conn)
                run_tool(
                    ["pg_dump", "-Fc", f"--snapshot={snapshot}", "-f", str(dump), "-d", url],
                    env,
                )
                conn.execute("ROLLBACK")
            run_tool(["pg_restore", "--list", str(dump)], env)
            size, sha = dump.stat().st_size, _sha256(dump)
            metadata = {
                "id": backup_id,
                "kind": kind,
                "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "environment": environment,
                "app_release": release,
                "alembic_revision": revision,
                "bytes": size,
                "sha256": sha,
                "row_counts": counts,
                "verified": False,
            }
            store.put_backup(backup_id, dump, metadata)

        stored = store.stat_dump(backup_id)
        if stored != (size, sha):
            raise OpsError(
                4,
                f"backup {backup_id} failed verification: stored object is {stored[0]} bytes "
                f"sha256 {stored[1]}, expected {size} bytes sha256 {sha}",
            )
        metadata["verified"] = True
        store.write_metadata(backup_id, metadata)
    except Exception as exc:
        message = f"Backup {backup_id} to {store.location} failed: {exc}"
        logger.error("backup failed", backup_id=backup_id, kind=kind, error=str(exc))
        alerts.notify(message, subject=f"Backup failed ({kind})")
        if isinstance(exc, OpsError) and exc.code == 4:
            raise
        raise OpsError(4, message) from exc

    deleted = select_deletions(_records(store), keep=keep, now=now)
    for old in deleted:
        store.delete(old)
    logger.info(
        "backup verified", backup_id=backup_id, kind=kind, bytes=size, deleted=deleted,
        row_counts=counts,
    )
    return {"backup_id": backup_id, "verified": True, "bytes": size, "deleted": deleted}
