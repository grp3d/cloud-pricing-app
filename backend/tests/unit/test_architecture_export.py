"""Unit tests for export serialization (014-architecture-templates-import-export, spec FR-015,
FR-016, SC-004; contracts/export-format.md).

Serialization runs over in-memory ORM objects; the round-trip test builds the re-imported copy
in the real test database with the shared builder, then serializes it again.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.models.orm import Architecture, Collection, DataConnector, SKUSelection, User
from src.services.architecture_transfer import (
    build_architecture,
    serialize_user_architectures,
    specs_from_definition,
    validate_definition,
)

T0 = datetime(2026, 9, 1, 12, 0, 0)
NOW = datetime(2026, 9, 25, 14, 30, 22, tzinfo=UTC)


def _sel(service_code: str, sku: str, qty: str, seconds: int) -> SKUSelection:
    return SKUSelection(
        id=uuid.uuid4(),
        service_code=service_code,
        sku=sku,
        pricing_term="on_demand",
        purchase_option="not_applicable",
        usage_quantity=Decimal(qty),
        created_at=T0 + timedelta(seconds=seconds),
    )


def _architecture(name: str = "Web App", deleted: bool = False) -> Architecture:
    vpc_east = Collection(
        id=uuid.uuid4(), type="vpc", name="VPC east", region="us-east-1",
        created_at=T0 + timedelta(seconds=1),
        sku_selections=[
            _sel("AmazonEC2", "SKU_A", "96", 10),
            _sel("AmazonS3", "SKU_B", "2000", 11),
        ],
    )
    vpc_west = Collection(
        id=uuid.uuid4(), type="vpc", name="VPC west", region="us-west-2",
        created_at=T0 + timedelta(seconds=2), sku_selections=[],
    )
    # Created *before* its parent in wall-clock terms is impossible in practice, but the
    # component is listed first here to prove export always emits parents first.
    component = Collection(
        id=uuid.uuid4(), type="application_component", name="Web tier", region="us-east-1",
        parent_collection_id=vpc_east.id, created_at=T0 + timedelta(seconds=3),
        sku_selections=[_sel("AmazonEC2", "SKU_C", "1.5", 12)],
    )
    removed = Collection(
        id=uuid.uuid4(), type="vpc", name="Removed VPC", region="us-east-1",
        created_at=T0 + timedelta(seconds=4), deleted_at=T0 + timedelta(days=1),
        sku_selections=[],
    )
    live_connector = DataConnector(
        id=uuid.uuid4(), from_collection_id=vpc_east.id, to_collection_id=vpc_west.id,
        created_at=T0 + timedelta(seconds=5),
        sku_selection=_sel("AWSDataTransfer", "SKU_DT", "8.0645", 13),
    )
    dangling_connector = DataConnector(
        id=uuid.uuid4(), from_collection_id=vpc_east.id, to_collection_id=removed.id,
        created_at=T0 + timedelta(seconds=6), sku_selection=None,
    )
    deleted_connector = DataConnector(
        id=uuid.uuid4(), from_collection_id=vpc_west.id, to_collection_id=vpc_east.id,
        created_at=T0 + timedelta(seconds=7), deleted_at=T0 + timedelta(days=1),
    )
    return Architecture(
        id=uuid.uuid4(), user_id=uuid.uuid4(), name=name, provider="aws", is_public=True,
        deleted_at=T0 if deleted else None,
        collections=[component, vpc_east, vpc_west, removed],
        connectors=[live_connector, dangling_connector, deleted_connector],
    )


def test_envelope_fields():
    export = serialize_user_architectures([_architecture()], username="jdoe", now=NOW)
    assert export.format == "cloud-pricing-architectures"
    assert export.format_version == 1
    assert export.source_username == "jdoe"
    assert export.exported_at == NOW


def test_deleted_architectures_are_excluded():
    export = serialize_user_architectures(
        [_architecture("Live"), _architecture("Gone", deleted=True)], username="jdoe", now=NOW
    )
    assert [a.name for a in export.architectures] == ["Live"]


def test_collections_parent_first_with_file_local_refs():
    [arch] = serialize_user_architectures([_architecture()], username="jdoe", now=NOW).architectures
    assert [(c.ref, c.name, c.parent_ref) for c in arch.collections] == [
        ("c1", "VPC east", None),
        ("c2", "VPC west", None),
        ("c3", "Web tier", "c1"),
    ]
    assert [(s.sku, s.usage_quantity) for s in arch.collections[0].sku_selections] == [
        ("SKU_A", Decimal("96")),
        ("SKU_B", Decimal("2000")),
    ]


def test_only_live_connectors_between_live_collections():
    [arch] = serialize_user_architectures([_architecture()], username="jdoe", now=NOW).architectures
    assert [(c.from_ref, c.to_ref) for c in arch.connectors] == [("c1", "c2")]
    assert arch.connectors[0].sku_selection.sku == "SKU_DT"


def test_json_has_no_ids_owner_visibility_or_prices():
    export = serialize_user_architectures([_architecture()], username="jdoe", now=NOW)
    raw = export.model_dump(mode="json")
    forbidden = {"id", "user_id", "is_public", "price", "deleted_at", "architecture_id"}

    def walk(node):
        if isinstance(node, dict):
            assert not forbidden & node.keys(), forbidden & node.keys()
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(raw)
    quantity = raw["architectures"][0]["collections"][2]["sku_selections"][0]["usage_quantity"]
    assert quantity == "1.5000"


async def test_round_trip_reproduces_the_architecture(db_session):
    """Export -> validate -> build -> export again yields the same definition (SC-004)."""
    [first] = serialize_user_architectures(
        [_architecture()], username="jdoe", now=NOW
    ).architectures
    raw = json.loads(first.model_dump_json())
    definition, error = validate_definition(
        raw,
        taken_names=set(),
        available_regions={"us-east-1", "us-west-2"},
        existing_skus=lambda region, pairs: pairs,
    )
    assert error is None

    owner = User(id=uuid.uuid4())
    db_session.add(owner)
    collections, connectors = specs_from_definition(definition)
    built = build_architecture(
        db_session, owner=owner, name=definition.name, provider=definition.provider,
        collections=collections, connectors=connectors,
    )
    await db_session.commit()
    assert built.is_public is False

    reloaded = (
        await db_session.execute(
            select(Architecture)
            .where(Architecture.id == built.id)
            .options(
                selectinload(Architecture.collections).selectinload(Collection.sku_selections),
                selectinload(Architecture.connectors).selectinload(DataConnector.sku_selection),
            )
        )
    ).scalar_one()
    [second] = serialize_user_architectures([reloaded], username="x", now=NOW).architectures
    assert second.model_dump() == first.model_dump()
