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
# A real m5.16xlarge instance SKU (009-ui-fixes-next-iteration, US1) whose own `product_dim` row
# is unreachable via free-text search before this fix — its own attributes_json says nothing
# about "2AB37QDFJZBGQ5YP" (that string only appears as its `sku` column value), while two
# *other* SKUs (Capacity-Reservation variants of the same instance type) reference it inside
# their own attributes_json as `instancesku`, so a naive fix that widened the match without also
# covering `p.sku` itself would keep finding the wrong rows.
KNOWN_SKU = "2AB37QDFJZBGQ5YP"
# Real AWSDataTransfer rows (009-ui-fixes-next-iteration, US9) used to exercise the new
# from_region_code/to_region_code filters against the live Parquet data.
KNOWN_FROM_REGION_CODE = "ap-southeast-2-per-1"
KNOWN_TO_REGION_CODE = "us-west-2-pdx-1"
KNOWN_FROM_TO_SKU = "28EK9CZBYC9JU7KW"  # fromRegionCode=us-east-1, toRegionCode=us-west-2-pdx-1


def test_service_code_regex_matches_case_insensitively():
    """`^AmazonEC2$` is an exact-match regex, but lowercased — the 'i' flag (research.md §2)
    must still match every row that a pre-008 exact `=` comparison would have."""
    results, _snapshot_date, total = search_catalog(
        service_code="^amazonec2$", limit=5, region="us-east-1"
    )
    assert total > 0
    assert all(r["service_code"] == KNOWN_SERVICE_CODE for r in results)


def test_product_family_regex_partial_match():
    results, _snapshot_date, total = search_catalog(
        product_family="^Compute Ins", limit=5, region="us-east-1"
    )
    assert total > 0
    assert all(r["product_family"] == KNOWN_PRODUCT_FAMILY for r in results)


def test_text_regex_matches_service_name():
    results, _snapshot_date, total = search_catalog(
        text="Elastic Compute", limit=5, region="us-east-1"
    )
    assert total > 0
    assert len(results) > 0


def test_text_regex_matches_the_skus_own_sku_column():
    """009-ui-fixes-next-iteration, US1, FR-001/research.md §1: searching free text for a SKU's
    own identifier MUST find that SKU's own `product_dim` row — before this fix, `text` only
    matched `service_name`/`attributes_json`, never the `sku` column itself, so pasting an exact
    SKU into search (a natural thing to do with a SKU ID in hand) silently failed to find it at
    all (while confusingly matching *other*, unrelated SKUs that happen to reference it inside
    their own attributes — see `KNOWN_SKU`'s docstring)."""
    results, _snapshot_date, total = search_catalog(text=KNOWN_SKU, limit=10, region="us-east-1")
    assert total >= 1
    assert any(r["sku"] == KNOWN_SKU for r in results)


def test_text_regex_sku_match_is_additive_not_a_replacement():
    """The same search must still surface the two other SKUs that legitimately mention this one
    in their `attributes_json` (`instancesku`) — the fix adds `sku` to the matched columns, it
    doesn't remove the existing `attributes_json` match (both are real, useful matches)."""
    results, _snapshot_date, _total = search_catalog(text=KNOWN_SKU, limit=10, region="us-east-1")
    skus_found = {r["sku"] for r in results}
    assert KNOWN_SKU in skus_found
    assert len(skus_found) >= 2  # the SKU itself, plus at least one attributes_json match


def test_invalid_service_code_pattern_raises_with_field_name():
    with pytest.raises(InvalidRegexPatternError) as excinfo:
        search_catalog(service_code="[unclosed", region="us-east-1")
    assert excinfo.value.field == "service_code"


def test_invalid_product_family_pattern_raises_with_field_name():
    with pytest.raises(InvalidRegexPatternError) as excinfo:
        search_catalog(product_family="(unclosed", region="us-east-1")
    assert excinfo.value.field == "product_family"


def test_invalid_text_pattern_raises_with_field_name():
    with pytest.raises(InvalidRegexPatternError) as excinfo:
        search_catalog(text="*nothing", region="us-east-1")
    assert excinfo.value.field == "text"


def test_total_is_independent_of_the_page_limit():
    """FR-024: `total` is the true count of every matching row, not just how many this page
    returned (capped by `limit`) — picking a filter known to match many rows with a small
    `limit` proves `total` isn't silently equal to `len(results)`."""
    results, _snapshot_date, total = search_catalog(
        service_code="AmazonEC2", limit=1, region="us-east-1"
    )
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
        "WHERE p.region_code = ? AND regexp_matches(p.service_code, ?, 'i')",
        [
            _product_dim_path(snapshot_date, "us-east-1"),
            _service_dim_path(snapshot_date, "us-east-1"),
            "us-east-1",
            "^AmazonEC2$",
        ],
    ).fetchone()[0]

    _results, _snapshot_date, total = search_catalog(
        service_code="^AmazonEC2$", limit=1, region="us-east-1"
    )

    assert total == expected_total


# 009-ui-fixes-next-iteration, US9, FR-029/contracts/api.md §2: from_region_code/to_region_code
# — two new optional filters, same case-insensitive RE2 regex convention as every existing
# filter, AND-combined with each other and with every other active filter.


def test_from_region_code_filters_matching_rows():
    results, _snapshot_date, total = search_catalog(
        service_code="^AWSDataTransfer$",
        from_region_code=f"^{KNOWN_FROM_REGION_CODE}$",
        limit=10,
        region="us-east-1",
    )
    assert total > 0
    assert all(r["attributes"].get("fromRegionCode") == KNOWN_FROM_REGION_CODE for r in results)


def test_to_region_code_filters_matching_rows():
    results, _snapshot_date, total = search_catalog(
        service_code="^AWSDataTransfer$",
        to_region_code=f"^{KNOWN_TO_REGION_CODE}$",
        limit=10,
        region="us-east-1",
    )
    assert total > 0
    assert all(r["attributes"].get("toRegionCode") == KNOWN_TO_REGION_CODE for r in results)


def test_from_and_to_region_code_and_combine():
    """Both filters together narrow to only rows matching *both* (AND, not OR) — proven by a
    known SKU whose from/to pair uniquely identifies it among the broader from-only/to-only
    result sets above."""
    results, _snapshot_date, total = search_catalog(
        service_code="^AWSDataTransfer$",
        from_region_code="^us-east-1$",
        to_region_code=f"^{KNOWN_TO_REGION_CODE}$",
        limit=10,
        region="us-east-1",
    )
    assert total > 0
    assert any(r["sku"] == KNOWN_FROM_TO_SKU for r in results)
    assert all(
        r["attributes"].get("fromRegionCode") == "us-east-1"
        and r["attributes"].get("toRegionCode") == KNOWN_TO_REGION_CODE
        for r in results
    )


def test_region_code_combines_with_existing_text_filter():
    """AND-combines with a pre-existing filter kind (text), not just with each other."""
    results, _snapshot_date, total = search_catalog(
        text="AWSDataTransfer",
        from_region_code=f"^{KNOWN_FROM_REGION_CODE}$",
        limit=10,
        region="us-east-1",
    )
    assert total > 0
    assert all(r["attributes"].get("fromRegionCode") == KNOWN_FROM_REGION_CODE for r in results)


def test_from_region_code_alone_satisfies_the_at_least_one_filter_requirement():
    """Setting only from_region_code (no service_code/product_family/text/to_region_code) must
    not raise EmptyCatalogFilterError — it counts as a filter in its own right."""
    results, _snapshot_date, total = search_catalog(
        from_region_code=f"^{KNOWN_FROM_REGION_CODE}$", limit=5, region="us-east-1"
    )
    assert total > 0


def test_to_region_code_alone_satisfies_the_at_least_one_filter_requirement():
    results, _snapshot_date, total = search_catalog(
        to_region_code=f"^{KNOWN_TO_REGION_CODE}$", limit=5, region="us-east-1"
    )
    assert total > 0


def test_invalid_from_region_code_pattern_raises_with_field_name():
    with pytest.raises(InvalidRegexPatternError) as excinfo:
        search_catalog(from_region_code="(unclosed", region="us-east-1")
    assert excinfo.value.field == "from_region_code"


def test_invalid_to_region_code_pattern_raises_with_field_name():
    with pytest.raises(InvalidRegexPatternError) as excinfo:
        search_catalog(to_region_code="(unclosed", region="us-east-1")
    assert excinfo.value.field == "to_region_code"


# --- Data-integrity finding (2026-09-15, live bug report): the upstream `product_dim`
# Parquet data is NOT actually filtered by its own `region=<code>` partition directory — every
# partition file contains the full multi-region catalog (verified directly: the `region=
# eu-west-1` partition has ~986k rows spanning every AWS region, not just eu-west-1's own
# ~165k). Each row DOES carry an accurate top-level `region_code` column, though, which
# `search_catalog()` must filter on explicitly rather than trusting partition selection alone.


# A real AmazonEC2 t3.medium SKU whose product_dim row's own `region_code` is `us-east-1`, even
# though it is present (verified directly against the real Parquet data) inside every other
# region's partition file too, including eu-west-1's.
KNOWN_US_EAST_1_ONLY_SKU = "NN4EGUUQRWVYP98C"
# A real AmazonEC2 t3.medium SKU whose product_dim row's own `region_code` is genuinely
# `eu-west-1` (verified directly against the real Parquet data).
KNOWN_EU_WEST_1_ONLY_SKU = "47NTBKB4KMUU98P8"


def test_search_excludes_a_sku_whose_own_region_code_does_not_match_the_requested_region():
    results, _snapshot_date, total = search_catalog(
        text=f"^{KNOWN_US_EAST_1_ONLY_SKU}$", region="eu-west-1", limit=10
    )
    assert total == 0
    assert results == []


def test_search_still_finds_that_sku_when_searching_its_own_region():
    results, _snapshot_date, total = search_catalog(
        text=f"^{KNOWN_US_EAST_1_ONLY_SKU}$", region="us-east-1", limit=10
    )
    assert total >= 1
    assert any(r["sku"] == KNOWN_US_EAST_1_ONLY_SKU for r in results)


def test_search_finds_a_genuinely_eu_west_1_sku_when_searching_eu_west_1():
    results, _snapshot_date, total = search_catalog(
        text=f"^{KNOWN_EU_WEST_1_ONLY_SKU}$", region="eu-west-1", limit=10
    )
    assert total >= 1
    assert any(r["sku"] == KNOWN_EU_WEST_1_ONLY_SKU for r in results)


def test_search_excludes_that_eu_west_1_sku_when_searching_us_east_1():
    results, _snapshot_date, total = search_catalog(
        text=f"^{KNOWN_EU_WEST_1_ONLY_SKU}$", region="us-east-1", limit=10
    )
    assert total == 0
    assert results == []


# --- Same finding, AWSDataTransfer case: its top-level `region_code` column is unreliable —
# unlike AmazonEC2's, it merely mirrors whichever partition copy happens to be read (verified
# directly: the same AWSDataTransfer sku's `region_code` is "us-east-1" when read from the
# us-east-1 partition and "eu-west-1" when read from the eu-west-1 partition, even though its
# own `fromRegionCode`/`toRegionCode` attributes stay identical either way). Region-scoping an
# AWSDataTransfer row must key off `fromRegionCode` instead (spec FR-006: a connector's search
# is scoped to its "from" collection's region).


def test_search_excludes_an_awsdatatransfer_sku_whose_own_fromregioncode_does_not_match():
    # KNOWN_FROM_TO_SKU's fromRegionCode is us-east-1 (see its own constant comment above) —
    # must not appear when scoped to a different region, regardless of region_code.
    results, _snapshot_date, total = search_catalog(
        text=f"^{KNOWN_FROM_TO_SKU}$", region="eu-west-1", limit=10
    )
    assert total == 0
    assert results == []


def test_search_finds_that_awsdatatransfer_sku_when_scoped_to_its_own_fromregioncode():
    results, _snapshot_date, total = search_catalog(
        text=f"^{KNOWN_FROM_TO_SKU}$", region="us-east-1", limit=10
    )
    assert total >= 1
    assert any(r["sku"] == KNOWN_FROM_TO_SKU for r in results)
