"""Unit tests for `list_available_regions()` (010-multi-region-support, spec FR-017).

Runs against the real Parquet pricing data (Constitution Principle I — no mock substitute),
mirroring `test_catalog_search.py`'s convention.
"""

from __future__ import annotations

from pathlib import Path

from src.config import settings
from src.pricing_data.regions import list_available_regions
from src.pricing_data.snapshot import _TABLES, resolve_latest_snapshot_date


def test_returns_regions_common_to_every_table_at_the_latest_snapshot():
    snapshot_date = resolve_latest_snapshot_date()
    expected: set[str] | None = None
    for table in _TABLES:
        table_dir = (
            Path(settings.aws_pricing_parquet_dir) / table / f"snapshot_date={snapshot_date}"
        )
        codes = {
            entry.name.removeprefix("region=")
            for entry in table_dir.iterdir()
            if entry.is_dir() and entry.name.startswith("region=")
        }
        expected = codes if expected is None else expected & codes

    assert expected is not None and expected
    assert set(list_available_regions()) == expected


def test_returns_a_sorted_list_with_no_duplicates():
    regions = list_available_regions()
    assert regions == sorted(set(regions))


def test_known_region_is_present():
    # us-east-1 is the app's former single global pricing region (spec FR-016) — must still be
    # present in the live multi-region dataset.
    assert "us-east-1" in list_available_regions()
