"""Unit tests for the architecture export-format validator
(014-architecture-templates-import-export, data-model.md › Validation rules,
contracts/export-format.md).

Pure logic — no database or Parquet access: region availability and SKU existence are injected,
so each rule can be exercised in isolation and in its documented order.
"""

from __future__ import annotations

import copy
from decimal import Decimal

import pytest

from src.services.architecture_transfer import (
    InvalidImportFileError,
    validate_definition,
    validate_envelope,
)

REGIONS = {"us-east-1", "us-west-2", "eu-west-1"}
KNOWN = {
    "us-east-1": {("AmazonEC2", "SKU_EC2"), ("AWSDataTransfer", "SKU_DT")},
    "us-west-2": {("AmazonS3", "SKU_S3")},
}


def _existing_skus(region: str, pairs: set[tuple[str, str]]) -> set[tuple[str, str]]:
    return pairs & KNOWN.get(region, set())


def _selection(service_code: str = "AmazonEC2", sku: str = "SKU_EC2", quantity="96.0000"):
    return {
        "service_code": service_code,
        "sku": sku,
        "pricing_term": "on_demand",
        "purchase_option": "not_applicable",
        "usage_quantity": quantity,
    }


def _definition(name: str = "Web App") -> dict:
    return {
        "name": name,
        "provider": "aws",
        "collections": [
            {
                "ref": "c1",
                "type": "vpc",
                "name": "VPC (us-east-1)",
                "region": "us-east-1",
                "parent_ref": None,
                "sku_selections": [_selection()],
            },
            {
                "ref": "c2",
                "type": "application_component",
                "name": "Web tier",
                "region": "us-east-1",
                "parent_ref": "c1",
                "sku_selections": [],
            },
            {
                "ref": "c3",
                "type": "vpc",
                "name": "VPC (us-west-2)",
                "region": "us-west-2",
                "parent_ref": None,
                "sku_selections": [_selection("AmazonS3", "SKU_S3", 2000)],
            },
        ],
        "connectors": [
            {
                "from_ref": "c1",
                "to_ref": "c3",
                "sku_selection": _selection("AWSDataTransfer", "SKU_DT", "8.0645"),
            }
        ],
    }


def _validate(raw: dict, taken: set[str] | None = None):
    return validate_definition(
        raw,
        taken_names=taken if taken is not None else set(),
        available_regions=REGIONS,
        existing_skus=_existing_skus,
    )


# --- validate_envelope (FR-019) ---


def _envelope(**overrides) -> dict:
    doc = {
        "format": "cloud-pricing-architectures",
        "format_version": 1,
        "exported_at": "2026-09-25T14:30:22Z",
        "source_username": "jdoe",
        "architectures": [],
    }
    doc.update(overrides)
    return doc


def test_valid_envelope_passes():
    validate_envelope(_envelope())


@pytest.mark.parametrize(
    "doc",
    [
        [],
        "not an object",
        None,
        _envelope(format="something-else"),
        _envelope(format_version=2),
        _envelope(format_version="1"),
        _envelope(architectures={"not": "a list"}),
        {k: v for k, v in _envelope().items() if k != "architectures"},
        {k: v for k, v in _envelope().items() if k != "format"},
        # The old baseline JSON shape from docs/functionality_2026-09-25.md.
        {"version": "1.0", "architectures": [{"id": "arch_x", "components": []}]},
    ],
)
def test_invalid_envelope_rejected_as_whole_file(doc):
    with pytest.raises(InvalidImportFileError):
        validate_envelope(doc)


# --- validate_definition, rules in data-model.md order ---


def test_valid_definition_returns_parsed_model():
    definition, error = _validate(_definition())
    assert error is None
    assert definition is not None
    assert definition.name == "Web App"
    assert [c.ref for c in definition.collections] == ["c1", "c2", "c3"]
    assert definition.collections[2].sku_selections[0].usage_quantity == Decimal("2000")
    assert definition.connectors[0].sku_selection.usage_quantity == Decimal("8.0645")


def test_unknown_extra_fields_are_ignored():
    raw = _definition()
    raw["future_field"] = {"anything": True}
    raw["collections"][0]["color"] = "blue"
    definition, error = _validate(raw)
    assert error is None and definition is not None


def test_rule1_malformed_entry():
    raw = _definition()
    del raw["collections"][0]["type"]
    definition, error = _validate(raw)
    assert definition is None
    assert error.startswith("Invalid architecture definition:")


def test_rule1_non_object_entry():
    definition, error = _validate(["not", "an", "object"])  # type: ignore[arg-type]
    assert definition is None
    assert error.startswith("Invalid architecture definition:")


def test_rule1_negative_quantity_rejected():
    raw = _definition()
    raw["collections"][0]["sku_selections"][0]["usage_quantity"] = "-1"
    _, error = _validate(raw)
    assert error.startswith("Invalid architecture definition:")


def test_rule2_name_already_taken():
    definition, error = _validate(_definition("Web App"), taken={"Web App"})
    assert definition is None
    assert error == "Architecture name already exists"


def test_rule2_name_compared_after_trimming():
    _, error = _validate(_definition("  Web App  "), taken={"Web App"})
    assert error == "Architecture name already exists"


def test_rule2_checked_before_structural_rules():
    raw = _definition()
    raw["connectors"][0]["to_ref"] = "c9"
    _, error = _validate(raw, taken={"Web App"})
    assert error == "Architecture name already exists"


def test_rule3_unknown_connector_ref():
    raw = _definition()
    raw["connectors"][0]["to_ref"] = "c9"
    _, error = _validate(raw)
    assert error == 'Invalid reference: connector points to unknown collection "c9"'


def test_rule3_unknown_parent_ref():
    raw = _definition()
    raw["collections"][1]["parent_ref"] = "c9"
    _, error = _validate(raw)
    assert error == 'Invalid reference: "Web tier" has unknown parent "c9"'


def test_rule3_duplicate_ref():
    raw = _definition()
    raw["collections"][2]["ref"] = "c1"
    _, error = _validate(raw)
    assert error == 'Invalid reference: duplicate collection ref "c1"'


def test_rule3_self_connector():
    raw = _definition()
    raw["connectors"][0]["to_ref"] = "c1"
    _, error = _validate(raw)
    assert error == 'Invalid reference: connector links collection "c1" to itself'


def test_rule4_vpc_with_parent():
    raw = _definition()
    raw["collections"][2]["parent_ref"] = "c1"
    _, error = _validate(raw)
    assert error == 'Invalid nesting: VPC "VPC (us-west-2)" cannot be nested'


def test_rule4_component_inside_component():
    raw = _definition()
    raw["collections"].append(
        {
            "ref": "c4",
            "type": "application_component",
            "name": "Worker",
            "region": "us-east-1",
            "parent_ref": "c2",
            "sku_selections": [],
        }
    )
    _, error = _validate(raw)
    assert error == 'Invalid nesting: "Worker" must be inside a VPC'


def test_rule4a_provider_not_supported():
    raw = _definition()
    raw["provider"] = "gcp"
    _, error = _validate(raw)
    assert error == "Provider not supported: gcp"


def test_rule5_region_not_available():
    raw = _definition()
    raw["collections"][2]["region"] = "ap-south-1"
    _, error = _validate(raw)
    assert error == "Region not available in pricing data: ap-south-1"


def test_rule6_missing_sku():
    raw = _definition()
    raw["collections"][0]["sku_selections"][0]["sku"] = "ZZZZZZZZZZZZZZZZ"
    _, error = _validate(raw)
    assert error == "Service not found in pricing data: AmazonEC2 / ZZZZZZZZZZZZZZZZ (us-east-1)"


def test_rule6_connector_sku_checked_in_from_collection_region():
    """The data-transfer SKU only exists in us-east-1 (the connector's `from` side); flipping
    the connector's direction must make it unresolvable (its region becomes us-west-2)."""
    raw = _definition()
    raw["connectors"][0]["from_ref"], raw["connectors"][0]["to_ref"] = "c3", "c1"
    _, error = _validate(raw)
    assert error == "Service not found in pricing data: AWSDataTransfer / SKU_DT (us-west-2)"


def test_quantity_accepts_number_and_string():
    raw = _definition()
    raw["collections"][0]["sku_selections"][0]["usage_quantity"] = 96
    definition, error = _validate(raw)
    assert error is None
    assert definition.collections[0].sku_selections[0].usage_quantity == Decimal("96")


def test_input_not_mutated():
    raw = _definition()
    snapshot = copy.deepcopy(raw)
    _validate(raw)
    assert raw == snapshot
