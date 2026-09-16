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
