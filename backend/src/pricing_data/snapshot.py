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

# 019 (research R1): each provider's own pricing tables (pipeline 004 data-model).
PROVIDER_TABLES: dict[str, tuple[str, ...]] = {
    "aws": ("service_dim", "product_dim", "product_attribute", "region_dim", "price_fact"),
    "azure": ("price_item", "price_item_savings_plan"),
    "gcp": ("service", "sku", "sku_price", "sku_price_tier"),
}
PROVIDERS: tuple[str, ...] = tuple(PROVIDER_TABLES)
PROVIDER_NAMES: dict[str, str] = {"aws": "AWS", "gcp": "GCP", "azure": "Azure"}

# The five AWS pricing tables (kept as a name for the AWS-only code paths).
TABLES = PROVIDER_TABLES["aws"]

# The location partition for prices that apply everywhere (Azure, GCP).
GLOBAL = "global"


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

    def files_with_global(self, table: str, location: str) -> list[str]:
        """A location's files plus the `global` partition's, which every location's lookups
        also read (019, research R5). Just the location's own when it is `global` or the
        snapshot has no `global` partition (AWS)."""
        files = self.files(table, location)
        if location != GLOBAL:
            files += self.files(table, GLOBAL)
        return files

    def regions(self, table: str) -> set[str]:
        return set(self.manifest.tables[table].regions)

    @property
    def tables(self) -> tuple[str, ...]:
        """This provider's pricing tables (019, research R1)."""
        return PROVIDER_TABLES[self.provider]

    def locations(self) -> list[str]:
        """Every location the snapshot has data for, as the manifest's `regions.succeeded`
        lists them (019). Includes `global` and Azure geographies; the provider adapter decides
        which are selectable regions (research R5)."""
        return sorted(self.manifest.regions.succeeded)

    def common_regions(self) -> set[str]:
        """Regions present in all of the provider's tables."""
        return set.intersection(*(self.regions(t) for t in self.tables))
