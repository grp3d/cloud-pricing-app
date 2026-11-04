"""Reading historical snapshots for the price history (019, research R10, T075).

- `file://`: snapshots are read in place, with no copy.
- S3: only the tables the provider's `comparable_prices` reads are downloaded, each file with
  the existing size and SHA-256 verification, into a temporary folder that is deleted as soon
  as the snapshot's price list is written. The active snapshot's verified cache entry is used
  as it is when it is the snapshot asked for, so a weekly update downloads nothing extra.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from src.config import settings
from src.pricing_data.active_snapshot import _read_manifest, state_for
from src.pricing_data.history.builder import WeekSnapshot
from src.pricing_data.manifest import Manifest
from src.pricing_data.snapshot import ActiveSnapshot
from src.pricing_data.storage import LocalStore, S3Store, Store


def list_manifests(store: Store, provider: str) -> list[Manifest]:
    """Every readable, valid manifest of `provider`, oldest first. A manifest the app can't use
    is left out; its week is then a gap."""
    found: list[Manifest] = []
    for snapshot_date in store.list_manifest_dates(provider):
        manifest = _read_manifest(store, provider, snapshot_date)
        if isinstance(manifest, Manifest):
            found.append(manifest)
    return found


def snapshot_opener(store: Store, tables: tuple[str, ...]):
    """The `open_snapshot` for `build_history` over `store`."""

    @contextmanager
    def open_snapshot(week: WeekSnapshot) -> Iterator[ActiveSnapshot]:
        manifest = week.manifest
        if isinstance(store, LocalStore):
            yield ActiveSnapshot.from_manifest(manifest, base_dir=store.root, pinned=False)
            return
        active = state_for(manifest.provider).active
        if active is not None and (active.snapshot_date, active.revision) == (
            manifest.snapshot_date, manifest.revision
        ):
            yield active
            return
        assert isinstance(store, S3Store)
        cache_dir = Path(settings.pricing_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f"history-{manifest.provider}-", dir=cache_dir))
        try:
            for table in tables:
                for region in manifest.tables[table].regions.values():
                    for data_file in region.files:
                        store.download(data_file.path, tmp / data_file.path, data_file.bytes,
                                       data_file.sha256)
            yield ActiveSnapshot.from_manifest(manifest, base_dir=tmp, pinned=False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    return open_snapshot
