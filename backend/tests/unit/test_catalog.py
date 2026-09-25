"""Unit tests for pure catalog helpers (003-service-selection-improvements, FR-001-FR-003;
004-canvas-pricing-improvements, FR-014).

`resolve_attributes` tests run against the real Parquet pricing data (Constitution Principle I —
no mock substitute), mirroring `test_pricing_units.py`'s `resolve_units` tests (003).
"""

from __future__ import annotations

from src.pricing_data.catalog import parse_attributes, resolve_attributes

# A known EC2 Compute Instance SKU (also used by tests/unit/test_pricing_units.py).
KNOWN_SKU = "NN4EGUUQRWVYP98C"
KNOWN_SERVICE_CODE = "AmazonEC2"


def test_parse_attributes_valid_json():
    raw = '{"instanceType": "t3.medium", "vcpu": "2"}'
    assert parse_attributes(raw) == {"instanceType": "t3.medium", "vcpu": "2"}


def test_parse_attributes_none_returns_empty_map():
    assert parse_attributes(None) == {}


def test_parse_attributes_empty_string_returns_empty_map():
    assert parse_attributes("") == {}


def test_parse_attributes_malformed_json_returns_empty_map_not_error():
    """Never fabricate or raise on bad data (Constitution Principle I) — a malformed value
    surfaces as "no details available" (FR-003), not a 500."""
    assert parse_attributes("{not valid json") == {}


def test_parse_attributes_non_object_json_returns_empty_map():
    """A JSON array or scalar isn't a valid attributes map — treat it like missing data."""
    assert parse_attributes("[1, 2, 3]") == {}
    assert parse_attributes('"just a string"') == {}


def test_parse_attributes_coerces_non_string_values():
    raw = '{"vcpu": 2, "supportsGpu": true}'
    assert parse_attributes(raw) == {"vcpu": "2", "supportsGpu": "True"}


def test_resolve_attributes_known_sku():
    result = resolve_attributes([(KNOWN_SERVICE_CODE, KNOWN_SKU)], region="us-east-1")
    assert result[(KNOWN_SERVICE_CODE, KNOWN_SKU)]["instanceType"] == "t3.medium"


def test_resolve_attributes_unknown_sku_returns_empty_map_not_missing_key():
    result = resolve_attributes(
        [(KNOWN_SERVICE_CODE, "THIS-SKU-DOES-NOT-EXIST")], region="us-east-1"
    )
    assert result[(KNOWN_SERVICE_CODE, "THIS-SKU-DOES-NOT-EXIST")] == {}


def test_resolve_attributes_batches_multiple_skus():
    other_sku = "2QF2GD6XUCJHFMKF"
    result = resolve_attributes(
        [(KNOWN_SERVICE_CODE, KNOWN_SKU), (KNOWN_SERVICE_CODE, other_sku)], region="us-east-1"
    )
    assert result[(KNOWN_SERVICE_CODE, KNOWN_SKU)] != {}
    assert result[(KNOWN_SERVICE_CODE, other_sku)] != {}


def test_resolve_attributes_empty_input_returns_empty_map():
    assert resolve_attributes([], region="us-east-1") == {}


# --- find_existing_skus (014-architecture-templates-import-export, research.md §9) ---

import pytest  # noqa: E402

from src.pricing_data.catalog import find_existing_skus  # noqa: E402
from src.pricing_data.errors import PricingDataUnavailableError  # noqa: E402

MISSING_SKU = "ZZZZZZZZZZZZZZZZ"


def test_find_existing_skus_returns_only_present_pairs():
    result = find_existing_skus(
        [(KNOWN_SERVICE_CODE, KNOWN_SKU), (KNOWN_SERVICE_CODE, MISSING_SKU)], region="us-east-1"
    )
    assert result == {(KNOWN_SERVICE_CODE, KNOWN_SKU)}


def test_find_existing_skus_is_region_scoped():
    """AWS SKU codes are region-scoped — the us-east-1 SKU doesn't exist in eu-west-1."""
    assert find_existing_skus([(KNOWN_SERVICE_CODE, KNOWN_SKU)], region="eu-west-1") == set()


def test_find_existing_skus_requires_service_code_to_match():
    assert find_existing_skus([("AmazonS3", KNOWN_SKU)], region="us-east-1") == set()


def test_find_existing_skus_empty_input_returns_empty_set_without_querying(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("must not query DuckDB for empty input")

    monkeypatch.setattr("src.pricing_data.catalog.duckdb.connect", _boom)
    assert find_existing_skus([], region="us-east-1") == set()


def test_find_existing_skus_wraps_duckdb_errors(monkeypatch):
    import duckdb

    def _fail(*args, **kwargs):
        raise duckdb.IOException("unreadable")

    monkeypatch.setattr("src.pricing_data.catalog.duckdb.connect", _fail)
    with pytest.raises(PricingDataUnavailableError):
        find_existing_skus([(KNOWN_SERVICE_CODE, KNOWN_SKU)], region="us-east-1")


# --- resolve_product_details (015-canvas-service-icons, research.md §2) ---

from src.pricing_data.catalog import ProductDetails, resolve_product_details  # noqa: E402

NAT_GATEWAY_SKU = "2QF2GD6XUCJHFMKF"  # AmazonEC2, product family "NAT Gateway", us-east-1
S3_NO_FAMILY_SKU = "3Q77AV5KBQJMTNXB"  # AmazonS3, empty product family, us-east-1
DATA_TRANSFER_SKU = "29ES3PB4K6NDYBAM"  # AWSDataTransfer, fromRegionCode us-east-1
FOREIGN_DATA_TRANSFER_SKU = "2PX8X4KYFH9H82XW"  # us-east-1 partition, fromRegionCode me-south-1


def test_resolve_product_details_returns_product_family_and_attributes():
    result = resolve_product_details([(KNOWN_SERVICE_CODE, NAT_GATEWAY_SKU)], region="us-east-1")
    details = result[(KNOWN_SERVICE_CODE, NAT_GATEWAY_SKU)]
    assert details.product_family == "NAT Gateway"
    assert details.attributes["usagetype"]


def test_resolve_product_details_empty_product_family_is_none():
    result = resolve_product_details([("AmazonS3", S3_NO_FAMILY_SKU)], region="us-east-1")
    assert result[("AmazonS3", S3_NO_FAMILY_SKU)].product_family is None


def test_resolve_product_details_missing_sku_is_empty_not_missing_key():
    """Same missing-data behavior as `resolve_attributes`: every requested key is present."""
    result = resolve_product_details([(KNOWN_SERVICE_CODE, MISSING_SKU)], region="us-east-1")
    assert result[(KNOWN_SERVICE_CODE, MISSING_SKU)] == ProductDetails(
        attributes={}, product_family=None
    )


def test_resolve_product_details_data_transfer_scoped_by_from_region():
    result = resolve_product_details(
        [("AWSDataTransfer", DATA_TRANSFER_SKU), ("AWSDataTransfer", FOREIGN_DATA_TRANSFER_SKU)],
        region="us-east-1",
    )
    assert result[("AWSDataTransfer", DATA_TRANSFER_SKU)].product_family == "Data Transfer"
    assert result[("AWSDataTransfer", FOREIGN_DATA_TRANSFER_SKU)].product_family is None


def test_resolve_product_details_empty_input_returns_empty_map_without_querying(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("must not query DuckDB for empty input")

    monkeypatch.setattr("src.pricing_data.catalog.duckdb.connect", _boom)
    assert resolve_product_details([], region="us-east-1") == {}


def test_resolve_attributes_matches_resolve_product_details_attributes():
    pairs = [(KNOWN_SERVICE_CODE, KNOWN_SKU), (KNOWN_SERVICE_CODE, NAT_GATEWAY_SKU)]
    details = resolve_product_details(pairs, region="us-east-1")
    assert resolve_attributes(pairs, region="us-east-1") == {
        key: value.attributes for key, value in details.items()
    }
