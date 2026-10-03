"""`ops db-init`: restore or initialize the database, then migrate (018-app-cloud-deployment,
FR-021–FR-024; research.md R8, contracts/ops-cli.md).

Runs once per bring-up, after Postgres is healthy and before the backend starts:

1. A database that already has `alembic_version` is `existing`: it is only migrated.
2. Otherwise the named backup, or the newest verified one, is restored and its row counts
   verified (`restored`). A backup from a newer release, or one that fails verification, stops
   the bring-up — and the database is wiped back to empty, so a rerun never mistakes a
   half-restored database for an existing one (FR-022).
3. With no backup at all, the database is created `fresh` and the default Admin's password is
   set from the owner-password parameter (FR-024).
4. `alembic upgrade head` in every case. Seed data comes only from the migrations (`0004` Admin,
   `0005` standard architectures), which insert with `WHERE NOT EXISTS`.

The result is written to `result_path` for `ops health`, on failure too.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from src.logging_config import get_logger
from src.ops import params
from src.ops.backup_store import BackupStore
from src.ops.db import (
    OpsError,
    alembic_revision,
    alembic_upgrade,
    connect,
    known_revisions,
    libpq,
    row_counts,
    run_tool,
)
from src.services.auth_service import hash_password

logger = get_logger("cloud_pricing.ops.db_init")


def _write_result(result_path: Path, result: dict) -> None:
    result_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = result_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result))
    tmp.replace(result_path)


def _wipe(database_url: str) -> None:
    """Return the database to empty after a failed restore."""
    with connect(database_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")


def _choose_backup(store: BackupStore, backup_id: str | None) -> dict | None:
    if backup_id is None:
        return store.newest_verified()
    metadata = store.get(backup_id)
    if metadata is None:
        raise OpsError(3, f"backup {backup_id} not found in {store.location}")
    if metadata.get("verified") is not True:
        raise OpsError(3, f"backup {backup_id} is not verified and can't be restored")
    return metadata


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _restore(database_url: str, store: BackupStore, metadata: dict) -> dict[str, int]:
    backup_id = metadata["id"]
    if metadata.get("alembic_revision") not in known_revisions():
        raise OpsError(
            3,
            f"backup {backup_id} is from a newer release (schema "
            f"{metadata.get('alembic_revision')}); deploy that release or choose an older backup",
        )
    with tempfile.TemporaryDirectory(prefix="cp-restore-") as tmp:
        dump = Path(tmp) / f"{backup_id}.dump"
        store.fetch_dump(backup_id, dump)
        actual = (dump.stat().st_size, _sha256(dump))
        if actual != (metadata["bytes"], metadata["sha256"]):
            raise OpsError(4, f"backup {backup_id} failed its checksum after download")
        url, env = libpq(database_url)
        try:
            run_tool(["pg_restore", "--no-owner", "--exit-on-error", "-d", url, str(dump)], env)
        except OpsError as exc:
            raise OpsError(4, f"backup {backup_id} could not be restored: {exc}") from exc
    with connect(database_url) as conn:
        counts = row_counts(conn)
    expected = metadata["row_counts"]
    mismatched = {t: (expected[t], counts.get(t)) for t in expected if counts.get(t) != expected[t]}
    if mismatched:
        raise OpsError(4, f"backup {backup_id} failed row-count verification: {mismatched}")
    return counts


def run_db_init(
    *,
    database_url: str,
    store: BackupStore | None,
    backup_id: str | None,
    owner_password_parameter: str | None,
    allow_default_admin_password: bool,
    result_path: Path,
) -> dict:
    try:
        result = _run(
            database_url=database_url,
            store=store,
            backup_id=backup_id,
            owner_password_parameter=owner_password_parameter,
            allow_default_admin_password=allow_default_admin_password,
        )
    except OpsError as exc:
        logger.error("db-init failed", error=str(exc), exit_code=exc.code)
        _write_result(result_path, {"db": "failed", "error": str(exc), "exit_code": exc.code})
        raise
    _write_result(result_path, result)
    logger.info("db-init finished", db=result["db"], backup_id=result["backup_id"],
                alembic_revision=result["alembic_revision"])
    return result


def _run(
    *,
    database_url: str,
    store: BackupStore | None,
    backup_id: str | None,
    owner_password_parameter: str | None,
    allow_default_admin_password: bool,
) -> dict:
    with connect(database_url) as conn:
        existing_revision = alembic_revision(conn)

    if existing_revision is not None:
        state, restored_from = "existing", None
    else:
        if store is None:
            raise OpsError(3, "BACKUP_URI is not set, so db-init can't look for a backup")
        metadata = _choose_backup(store, backup_id)
        if metadata is not None:
            try:
                _restore(database_url, store, metadata)
            except OpsError:
                _wipe(database_url)
                raise
            state, restored_from = "restored", metadata["id"]
        else:
            state, restored_from = "fresh", None

    owner_password: str | None = None
    if state == "fresh":
        if owner_password_parameter:
            owner_password = params.get_parameter(owner_password_parameter)
        elif not allow_default_admin_password:
            raise OpsError(
                3,
                "fresh database but OWNER_PASSWORD_PARAMETER is not set; refusing to keep the "
                "default Admin password (use --allow-default-admin-password only locally)",
            )

    alembic_upgrade(database_url)

    with connect(database_url) as conn:
        if owner_password is not None:
            conn.execute(
                "UPDATE users SET password_hash = %s WHERE is_default_admin",
                (hash_password(owner_password),),
            )
            conn.commit()
        counts = row_counts(conn)
        revision = alembic_revision(conn)

    return {
        "db": state,
        "backup_id": restored_from,
        "alembic_revision": revision,
        "row_counts": counts,
    }
