"""Unit tests for `list_available_regions()` (010-multi-region-support, spec FR-017).

Runs against the real Parquet pricing data (Constitution Principle I — no mock substitute),
mirroring `test_catalog_search.py`'s convention.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.config import settings
from src.pricing_data.regions import list_available_regions
from src.pricing_data.snapshot import TABLES


def test_returns_regions_common_to_every_table_at_the_latest_snapshot():
    """018-app-cloud-deployment: computed here straight from the manifest JSON on disk."""
    root = Path(settings.pricing_data_source.root)
    latest = json.loads((root / "aws/manifests/latest.json").read_text())
    manifest = json.loads((root / latest["manifest_path"]).read_text())
    expected: set[str] | None = None
    for table in TABLES:
        codes = set(manifest["tables"][table]["regions"])
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
