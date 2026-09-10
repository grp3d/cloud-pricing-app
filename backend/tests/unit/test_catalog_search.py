"""Unit tests for `search_catalog()`'s regex matching and total count (008-ui-updates-
corrections, US7, FR-020/021/024, research.md §2/§3).

Runs against the real Parquet pricing data (Constitution Principle I — no mock substitute),
mirroring `test_catalog.py`'s `resolve_attributes` tests and `test_pricing_units.py`'s
`resolve_units` tests.
"""

from __future__ import annotations

import duckdb
import pytest

from src.pricing_data.catalog import (
    InvalidRegexPatternError,
    _product_dim_path,
    _service_dim_path,
    search_catalog,
)
from src.pricing_data.snapshot import resolve_latest_snapshot_date

KNOWN_SERVICE_CODE = "AmazonEC2"
KNOWN_PRODUCT_FAMILY = "Compute Instance"


def test_service_code_regex_matches_case_insensitively():
    """`^AmazonEC2$` is an exact-match regex, but lowercased — the 'i' flag (research.md §2)
    must still match every row that a pre-008 exact `=` comparison would have."""
    results, _snapshot_date, total = search_catalog(service_code="^amazonec2$", limit=5)
    assert total > 0
    assert all(r["service_code"] == KNOWN_SERVICE_CODE for r in results)


def test_product_family_regex_partial_match():
    results, _snapshot_date, total = search_catalog(
        product_family="^Compute Ins", limit=5
    )
    assert total > 0
    assert all(r["product_family"] == KNOWN_PRODUCT_FAMILY for r in results)


def test_text_regex_matches_service_name():
    results, _snapshot_date, total = search_catalog(text="Elastic Compute", limit=5)
    assert total > 0
    assert len(results) > 0


def test_invalid_service_code_pattern_raises_with_field_name():
    with pytest.raises(InvalidRegexPatternError) as excinfo:
        search_catalog(service_code="[unclosed")
    assert excinfo.value.field == "service_code"


def test_invalid_product_family_pattern_raises_with_field_name():
    with pytest.raises(InvalidRegexPatternError) as excinfo:
        search_catalog(product_family="(unclosed")
    assert excinfo.value.field == "product_family"


def test_invalid_text_pattern_raises_with_field_name():
    with pytest.raises(InvalidRegexPatternError) as excinfo:
        search_catalog(text="*nothing")
    assert excinfo.value.field == "text"


def test_total_is_independent_of_the_page_limit():
    """FR-024: `total` is the true count of every matching row, not just how many this page
    returned (capped by `limit`) — picking a filter known to match many rows with a small
    `limit` proves `total` isn't silently equal to `len(results)`."""
    results, _snapshot_date, total = search_catalog(service_code="AmazonEC2", limit=1)
    assert len(results) == 1
    assert total > 1


def test_total_matches_independent_count_query():
    """Cross-checks `total` against a hand-written `COUNT(*)` over the same Parquet data and
    the same filter clause, computed independently of `search_catalog`'s own total query
    (Constitution Principle I: never estimate/guess — this proves it's a real count)."""
    snapshot_date = resolve_latest_snapshot_date()
    con = duckdb.connect(":memory:", read_only=False)
    expected_total = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) p "
        "JOIN read_parquet(?) s USING (service_code) "
        "WHERE regexp_matches(p.service_code, ?, 'i')",
        [
            _product_dim_path(snapshot_date),
            _service_dim_path(snapshot_date),
            "^AmazonEC2$",
        ],
    ).fetchone()[0]

    _results, _snapshot_date, total = search_catalog(service_code="^AmazonEC2$", limit=1)

    assert total == expected_total
