"""Unit tests for pure catalog helpers (003-service-selection-improvements, FR-001-FR-003)."""

from __future__ import annotations

from src.pricing_data.catalog import parse_attributes


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
