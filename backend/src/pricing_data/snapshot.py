"""Resolve which AWS pricing snapshot date to query.

The Parquet tables (service_dim/, product_dim/, product_attribute/, region_dim/, price_fact/)
are each independently partitioned by `snapshot_date=YYYY-MM-DD`. Per research.md #2 and
Constitution Principle I, a single request must pin one snapshot date and use it consistently
across all five tables, so a price is never computed from a mix of two different days' data.
"""

from __future__ import annotations

from pathlib import Path

from src.config import settings
from src.pricing_data.errors import PricingDataUnavailableError

_TABLES = ("service_dim", "product_dim", "product_attribute", "region_dim", "price_fact")


def _snapshot_dates(table: str) -> set[str]:
    table_dir = Path(settings.aws_pricing_parquet_dir) / table
    if not table_dir.is_dir():
        raise PricingDataUnavailableError(f"pricing data table directory not found: {table_dir}")
    dates = set()
    for entry in table_dir.iterdir():
        if entry.is_dir() and entry.name.startswith("snapshot_date="):
            dates.add(entry.name.removeprefix("snapshot_date="))
    return dates


def resolve_latest_snapshot_date() -> str:
    """Return the newest `snapshot_date` (YYYY-MM-DD) present in every one of the five tables.

    Raises PricingDataUnavailableError if the data directory is unreadable or no date is
    common to all five tables (a partially-refreshed data drop) — never silently falls back to
    a per-table "latest", which could mix two different days' data within one calculation.
    """
    try:
        common = None
        for table in _TABLES:
            dates = _snapshot_dates(table)
            common = dates if common is None else common & dates
        if not common:
            raise PricingDataUnavailableError(
                "no snapshot_date is common to all pricing tables"
            )
        return max(common)
    except OSError as exc:
        raise PricingDataUnavailableError(str(exc)) from exc
