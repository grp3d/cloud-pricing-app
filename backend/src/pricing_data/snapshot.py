"""The active pricing snapshot as one immutable value (018-app-cloud-deployment, FR-004, FR-009,
FR-059; data-model.md §5).

A snapshot is one revision of one date, described by the pipeline's manifest. Every pricing
request takes the active `ActiveSnapshot` once, at its start, and reads only the files its
manifest lists (`files`), so a request never mixes two snapshots or two revisions, and a folder
holding a superseded revision's leftovers is never double-counted (Constitution Principle I).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.pricing_data.manifest import Manifest

# The five pricing tables every snapshot has.
TABLES = ("service_dim", "product_dim", "product_attribute", "region_dim", "price_fact")


@dataclass(frozen=True)
class ActiveSnapshot:
    provider: str
    snapshot_date: str
    revision: int
    manifest: Manifest = field(repr=False, compare=False)
    # The local source root, or the snapshot's verified cache entry for an S3 source.
    base_dir: Path
    pinned: bool = False

    @classmethod
    def from_manifest(cls, manifest: Manifest, *, base_dir: Path, pinned: bool) -> ActiveSnapshot:
        return cls(
            provider=manifest.provider,
            snapshot_date=manifest.snapshot_date,
            revision=manifest.revision,
            manifest=manifest,
            base_dir=base_dir,
            pinned=pinned,
        )

    def files(self, table: str, region: str) -> list[str]:
        """Absolute paths of the manifest's files for one table and region (empty if none)."""
        entry = self.manifest.tables[table].regions.get(region)
        if entry is None:
            return []
        return [str(self.base_dir / f.path) for f in entry.files]

    def regions(self, table: str) -> set[str]:
        return set(self.manifest.tables[table].regions)

    def common_regions(self) -> set[str]:
        """Regions present in all five tables."""
        return set.intersection(*(self.regions(t) for t in TABLES))
