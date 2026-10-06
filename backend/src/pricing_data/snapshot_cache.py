"""The verified local copy of S3 snapshots (018-app-cloud-deployment, FR-009–FR-011;
data-model.md §4, research.md R7).

`ensure_cached` copies a snapshot's files to `<cache>/<provider>/<date>-r<revision>.tmp-<random>/`
at their manifest paths, checks each file's size and sha256 as it streams, writes
`cache-entry.json`, and renames the directory to `<date>-r<revision>/` in one step. A directory
with `cache-entry.json` is a verified entry and is never fetched again, including after a restart
(FR-010). Leftover `.tmp-*` directories are partial copies and are deleted at startup.

If the fetch outlasts the pipeline's grace period for superseded files, or a listed file has
already been deleted, the manifest is re-read and the fetch restarts with the newer revision
(storage-layout.md, consumer rule 7).
"""

from __future__ import annotations

import json
import secrets
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.pricing_data.manifest import Manifest, manifest_key, validate_manifest
from src.pricing_data.storage import ObjectMissingError, S3Store, VerificationError

ENTRY_FILE = "cache-entry.json"
# The pipeline's SUPERSEDED_FILE_GRACE_MINUTES default.
DEFAULT_GRACE_SECONDS = 5 * 60
_MAX_RESTARTS = 5


class CacheError(RuntimeError):
    """A snapshot could not be cached; the reason is shown in the Admin tab."""


@dataclass(frozen=True)
class CachedSnapshot:
    path: Path
    manifest: Manifest


@dataclass(frozen=True)
class CacheEntry:
    path: Path
    snapshot_date: str
    revision: int
    bytes: int
    verified_at: str


class _Restart(Exception):
    def __init__(self, manifest: Manifest) -> None:
        self.manifest = manifest


def entry_name(manifest: Manifest) -> str:
    return f"{manifest.snapshot_date}-r{manifest.revision}"


def _reread(store: S3Store, manifest: Manifest) -> Manifest | None:
    """The date's current manifest, if it is a usable, newer revision."""
    raw = store.get(manifest_key(manifest.provider, manifest.snapshot_date))
    if raw is None:
        return None
    try:
        current = Manifest.model_validate_json(raw)
    except ValueError:
        return None
    usable = validate_manifest(current, manifest.provider)
    if isinstance(usable, Manifest) and usable.revision > manifest.revision:
        return usable
    return None


def _fetch(
    store: S3Store,
    manifest: Manifest,
    provider_dir: Path,
    clock: Callable[[], float],
    grace_seconds: float,
) -> Path:
    entry = provider_dir / entry_name(manifest)
    tmp = provider_dir / f"{entry_name(manifest)}.tmp-{secrets.token_hex(4)}"
    started = clock()
    try:
        for data_file in manifest.files():
            try:
                store.download(data_file.path, tmp / data_file.path, data_file.bytes,
                               data_file.sha256)
            except ObjectMissingError as exc:
                newer = _reread(store, manifest)
                if newer is not None:
                    raise _Restart(newer) from exc
                raise CacheError(f"{data_file.path} is listed but missing from the source") from exc
            except VerificationError as exc:
                raise CacheError(str(exc)) from exc
            except (CacheError, _Restart):
                raise
            except Exception as exc:  # noqa: BLE001 — S3 errors become a reported reason
                raise CacheError(f"downloading {data_file.path} failed: {exc}") from exc
            if clock() - started > grace_seconds:
                newer = _reread(store, manifest)
                if newer is not None:
                    raise _Restart(newer)
                started = clock()
        (tmp / ENTRY_FILE).write_text(json.dumps({
            "provider": manifest.provider,
            "snapshot_date": manifest.snapshot_date,
            "revision": manifest.revision,
            "run_id": manifest.run_id,
            "total_bytes": manifest.total_bytes,
            "verified_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "manifest": manifest.model_dump(mode="json"),
        }))
        tmp.rename(entry)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return entry


def ensure_cached(
    store: S3Store,
    manifest: Manifest,
    cache_dir: Path,
    max_bytes: int,
    *,
    clock: Callable[[], float] = time.monotonic,
    grace_seconds: float = DEFAULT_GRACE_SECONDS,
    disk_free: Callable[[Path], object] = shutil.disk_usage,
) -> CachedSnapshot:
    """The verified local copy of `manifest`'s snapshot, downloading it if needed. Raises
    `CacheError` (leaving no entry) when it can't be cached; the caller keeps its current
    snapshot. The returned manifest may be a newer revision if the source moved on mid-fetch."""
    provider_dir = cache_dir / manifest.provider
    for _ in range(_MAX_RESTARTS):
        entry = provider_dir / entry_name(manifest)
        if (entry / ENTRY_FILE).is_file():
            return CachedSnapshot(entry, manifest)
        total = manifest.total_bytes
        if total > max_bytes:
            raise CacheError(
                f"snapshot {manifest.snapshot_date} r{manifest.revision} is {total} bytes, over "
                f"PRICING_CACHE_MAX_BYTES ({max_bytes})"
            )
        provider_dir.mkdir(parents=True, exist_ok=True)
        free = disk_free(provider_dir).free
        if total > free:
            raise CacheError(
                f"snapshot {manifest.snapshot_date} r{manifest.revision} is {total} bytes but only "
                f"{free} bytes are free in {cache_dir}"
            )
        try:
            return CachedSnapshot(_fetch(store, manifest, provider_dir, clock, grace_seconds),
                                  manifest)
        except _Restart as restart:
            manifest = restart.manifest
    raise CacheError(f"snapshot {manifest.snapshot_date} kept changing while it was downloaded")


def list_entries(cache_dir: Path, provider: str) -> list[CacheEntry]:
    """Verified entries, oldest first. Partial `.tmp-*` directories are not entries."""
    provider_dir = cache_dir / provider
    if not provider_dir.is_dir():
        return []
    entries = []
    for path in provider_dir.iterdir():
        meta = path / ENTRY_FILE
        if ".tmp-" in path.name or not meta.is_file():
            continue
        try:
            data = json.loads(meta.read_text())
        except (OSError, ValueError):
            continue
        entries.append(CacheEntry(path, data["snapshot_date"], data["revision"],
                                  data["total_bytes"], data["verified_at"]))
    return sorted(entries, key=lambda e: (e.snapshot_date, e.revision))


def startup_cleanup(cache_dir: Path) -> None:
    """Delete partial copies left by a restart mid-fetch."""
    if not cache_dir.is_dir():
        return
    for tmp in cache_dir.glob("*/*.tmp-*"):
        shutil.rmtree(tmp, ignore_errors=True)


# --- Clean-up (FR-011, SC-006) ------------------------------------------------------------------


def plan_cleanup(
    entries: list[CacheEntry],
    *,
    active: CacheEntry | None,
    keep: int,
    max_bytes: int,
    superseded_this_check: CacheEntry | None,
    purged_dates: set[str],
) -> list[Path]:
    """Paths of the entries to delete, oldest first. Pure: decides, deletes nothing.

    The active entry is never deleted, and neither is the one this check just superseded — a
    request may still be reading it; it becomes eligible at the next check. After that, purged
    snapshots go, then anything beyond `keep` others, then the oldest until the cache fits in
    `max_bytes`.
    """
    protected = {e.path for e in (active, superseded_this_check) if e is not None}
    oldest_first = sorted(entries, key=lambda e: (e.snapshot_date, e.revision))
    deletions: list[Path] = []

    for entry in oldest_first:
        if entry.path not in protected and entry.snapshot_date in purged_dates:
            deletions.append(entry.path)

    others = [e for e in oldest_first if active is None or e.path != active.path]
    others = [e for e in others if e.path not in deletions]
    excess = len(others) - keep
    for entry in others:
        if excess <= 0:
            break
        if entry.path not in protected:
            deletions.append(entry.path)
            excess -= 1

    remaining = [e for e in oldest_first if e.path not in deletions]
    total = sum(e.bytes for e in remaining)
    for entry in remaining:
        if total <= max_bytes:
            break
        if entry.path not in protected:
            deletions.append(entry.path)
            total -= entry.bytes

    return sorted(set(deletions), key=lambda p: p.name)


def apply_cleanup(paths: list[Path]) -> None:
    for path in paths:
        shutil.rmtree(path, ignore_errors=True)
