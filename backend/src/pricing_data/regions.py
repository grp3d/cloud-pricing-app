"""List the AWS regions the pricing dataset currently has data for (010-multi-region-support,
spec FR-017, research.md §3).

A plain filesystem directory listing of the active snapshot's region partitions (016: the date
comes from `active_snapshot.get_active_snapshot_date()`), not a DuckDB query — cheap enough to
call directly wherever a region needs validating, with no caching layer (Constitution
Principle VI).
"""

from __future__ import annotations

from pathlib import Path

from src.config import settings
from src.pricing_data.active_snapshot import get_active_snapshot_date
from src.pricing_data.errors import PricingDataUnavailableError

_TABLES = ("service_dim", "product_dim", "product_attribute", "region_dim", "price_fact")


def _region_codes(table: str, snapshot_date: str) -> set[str]:
    snapshot_dir = Path(settings.aws_pricing_parquet_dir) / table / f"snapshot_date={snapshot_date}"
    if not snapshot_dir.is_dir():
        raise PricingDataUnavailableError(
            f"pricing data snapshot directory not found: {snapshot_dir}"
        )
    codes = set()
    for entry in snapshot_dir.iterdir():
        if entry.is_dir() and entry.name.startswith("region="):
            codes.add(entry.name.removeprefix("region="))
    return codes


def list_available_regions() -> list[str]:
    """Return every region code present in all 5 pricing tables at the active snapshot date,
    sorted. Raises `PricingDataUnavailableError` if the data
    directory is unreadable or no region is common to all five tables — the same "never mix
    partial data" posture the active snapshot takes for dates.
    """
    snapshot_date = get_active_snapshot_date()
    try:
        common: set[str] | None = None
        for table in _TABLES:
            codes = _region_codes(table, snapshot_date)
            common = codes if common is None else common & codes
        if not common:
            raise PricingDataUnavailableError("no region is common to all pricing tables")
        return sorted(common)
    except OSError as exc:
        raise PricingDataUnavailableError(str(exc)) from exc
