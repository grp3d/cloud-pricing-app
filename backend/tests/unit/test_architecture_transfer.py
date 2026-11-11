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
    specs_from_definition,
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
        # The old baseline JSON shape from docs/brief/functionality_2026-09-25.md.
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


def test_rule4a_provider_not_supported(monkeypatch):
    """019 (US1): GCP and Azure have adapters now, so rule 4a fails only for a provider with
    none (simulated here; the file format names only the three providers)."""
    from src.services import architecture_transfer

    monkeypatch.setattr(architecture_transfer, "has_adapter", lambda code: code == "aws")
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


# --- 019 (T038, research R15): provider options in the file -----------------------------------


def test_provider_options_are_read_and_written():
    raw = _definition()
    raw["provider"] = "azure"
    raw["collections"][0]["sku_selections"][0]["provider_options"] = {
        "kind": "azure_vm", "version": 1, "os": "windows"}
    definition, error = _validate(raw)
    assert error is None
    collections, _ = specs_from_definition(definition)
    assert collections[0].sku_selections[0].provider_options == {
        "kind": "azure_vm", "version": 1, "os": "windows"}


def test_an_older_file_without_the_new_fields_still_validates():
    definition, error = _validate(_definition())
    assert error is None
    collections, _ = specs_from_definition(definition)
    assert collections[0].sku_selections[0].provider_options is None


def test_invalid_provider_options_fail_rule_1():
    raw = _definition()
    raw["collections"][0]["sku_selections"][0]["provider_options"] = {"kind": "gcp_machine",
                                                                      "vcpus": 0}
    _, error = _validate(raw)
    assert error.startswith("Invalid architecture definition:")


# --- 019 (T097, research R15): connector arrows in the file and in a copy ---------------------


def test_arrow_fields_are_read():
    raw = _definition()
    raw["connectors"][0].update(arrow_style="one_way", arrow_reversed=True)
    definition, error = _validate(raw)
    assert error is None
    _, connectors = specs_from_definition(definition)
    assert (connectors[0].arrow_style, connectors[0].arrow_reversed) == ("one_way", True)


def test_an_older_file_imports_connectors_with_their_old_arrowhead():
    # Before 019 every connector was drawn with an arrowhead at its `to` end.
    definition, error = _validate(_definition())
    assert error is None
    _, connectors = specs_from_definition(definition)
    assert (connectors[0].arrow_style, connectors[0].arrow_reversed) == ("one_way", False)


def test_an_explicit_none_style_is_kept():
    raw = _definition()
    raw["connectors"][0]["arrow_style"] = "none"
    definition, _error = _validate(raw)
    _, connectors = specs_from_definition(definition)
    assert connectors[0].arrow_style == "none"


def test_an_unknown_arrow_style_fails_rule_1():
    raw = _definition()
    raw["connectors"][0]["arrow_style"] = "zigzag"
    _, error = _validate(raw)
    assert error.startswith("Invalid architecture definition:")


def _arrowed_architecture():
    import uuid

    from src.models.orm import Architecture, Collection, DataConnector

    a = Collection(id=uuid.uuid4(), type="vpc", name="A", region="us-east-1", sku_selections=[])
    b = Collection(id=uuid.uuid4(), type="vpc", name="B", region="us-east-1", sku_selections=[])
    connector = DataConnector(id=uuid.uuid4(), from_collection_id=a.id, to_collection_id=b.id,
                              arrow_style="two_way", arrow_reversed=True, sku_selection=None)
    return Architecture(id=uuid.uuid4(), name="Arrows", provider="aws", collections=[a, b],
                        connectors=[connector])


def test_arrow_fields_are_written_and_round_trip():
    from src.services.architecture_transfer import serialize_architecture

    exported = serialize_architecture(_arrowed_architecture()).model_dump(mode="json")
    (connector,) = exported["connectors"]
    assert (connector["arrow_style"], connector["arrow_reversed"]) == ("two_way", True)
    definition, error = _validate(exported)
    assert error is None
    _, connectors = specs_from_definition(definition)
    assert (connectors[0].arrow_style, connectors[0].arrow_reversed) == ("two_way", True)


@pytest.mark.asyncio
async def test_a_copy_keeps_the_arrows(db_session):
    import uuid

    from sqlalchemy import select

    from src.models.orm import Architecture, Collection, DataConnector, User
    from src.services.architecture_import import import_architecture

    owner, importer = User(id=uuid.uuid4()), User(id=uuid.uuid4())
    db_session.add_all([owner, importer])
    source = Architecture(id=uuid.uuid4(), user_id=owner.id, provider="aws", name="Src")
    a = Collection(id=uuid.uuid4(), architecture=source, type="vpc", name="A",
                   region="us-east-1")
    b = Collection(id=uuid.uuid4(), architecture=source, type="vpc", name="B",
                   region="us-east-1")
    db_session.add_all([source, a, b])
    await db_session.flush()
    db_session.add(DataConnector(architecture_id=source.id, from_collection_id=a.id,
                                 to_collection_id=b.id, arrow_style="one_way",
                                 arrow_reversed=True))
    await db_session.commit()
    reloaded = (await db_session.execute(
        select(Architecture).where(Architecture.id == source.id))).scalar_one()
    await db_session.refresh(reloaded, attribute_names=["collections", "connectors"])
    for collection in reloaded.collections:
        await db_session.refresh(collection, attribute_names=["sku_selections"])
    for conn in reloaded.connectors:
        await db_session.refresh(conn, attribute_names=["sku_selection"])

    copy = await import_architecture(db_session, reloaded, importer, "Copy")
    (copied,) = (await db_session.execute(
        select(DataConnector).where(DataConnector.architecture_id == copy.id))).scalars().all()
    assert (copied.arrow_style, copied.arrow_reversed) == ("one_way", True)
