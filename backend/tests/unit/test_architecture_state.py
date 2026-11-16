"""025 (research R2, data-model §1): the architecture state and its fingerprint, without a
database."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import inspect

from src.models.orm import Architecture, Collection, DataConnector, SKUSelection
from src.services.architecture_state import (
    CollectionState,
    ConnectorState,
    ServiceState,
    fingerprint,
    state_of,
    to_transient,
)

T0 = datetime(2026, 11, 15, 12, 0, 0)

# Columns that aren't content: bookkeeping, or kept by soft delete rather than the state.
NOT_CONTENT = {"updated_at", "deleted_at", "architecture_id"}
RENAMED = {"parent_collection_id": "parent_id", "from_collection_id": "from_id",
           "to_collection_id": "to_id"}


def _architecture() -> Architecture:
    architecture = Architecture(id=uuid.uuid4(), name="Prod Web", provider="aws", is_public=False)
    vpc = Collection(id=uuid.uuid4(), type="vpc", name="VPC", region="us-east-1", created_at=T0)
    app = Collection(id=uuid.uuid4(), type="application_component", name="Web",
                     region="us-east-1", parent_collection_id=vpc.id, created_at=T0)
    other = Collection(id=uuid.uuid4(), type="vpc", name="DR", region="us-west-2", created_at=T0)
    gone = Collection(id=uuid.uuid4(), type="vpc", name="Old", region="us-east-1",
                      created_at=T0, deleted_at=T0)
    for c in (vpc, app, other, gone):
        c.sku_selections = []
    app.sku_selections = [SKUSelection(id=uuid.uuid4(), collection_id=app.id,
                                       service_code="AmazonEC2", sku="ABC",
                                       pricing_term="on_demand", purchase_option="not_applicable",
                                       usage_quantity=Decimal("744"), created_at=T0)]
    connector = DataConnector(id=uuid.uuid4(), from_collection_id=vpc.id,
                              to_collection_id=other.id, arrow_style="one_way",
                              arrow_reversed=False, created_at=T0)
    connector.sku_selection = SKUSelection(
        id=uuid.uuid4(), connector_id=connector.id, service_code="AWSDataTransfer", sku="DT",
        pricing_term="on_demand", purchase_option="not_applicable",
        usage_quantity=Decimal("100"), created_at=T0)
    architecture.collections = [vpc, app, other, gone]
    architecture.connectors = [connector]
    return architecture


def test_state_skips_deleted_rows_and_keeps_ids():
    architecture = _architecture()
    state = state_of(architecture)
    assert [c.name for c in state.collections] == ["VPC", "Web", "DR"]
    assert len(state.services) == 2 and len(state.connectors) == 1
    assert state.collections[1].parent_id == state.collections[0].id


def test_state_covers_every_saved_column():
    for model, fields in ((Collection, CollectionState.model_fields),
                          (SKUSelection, ServiceState.model_fields),
                          (DataConnector, ConnectorState.model_fields)):
        columns = {c.key for c in inspect(model).column_attrs} - NOT_CONTENT
        assert {RENAMED.get(c, c) for c in columns} == set(fields), model.__name__


def test_fingerprint_is_stable_and_order_free():
    one = state_of(_architecture())
    two = one.model_copy(deep=True)
    two.collections.reverse()
    two.services.reverse()
    assert fingerprint(one) == fingerprint(two)


def test_fingerprint_changes_with_any_content_change():
    base = state_of(_architecture())
    changes = [
        lambda s: setattr(s, "name", "Renamed"),
        lambda s: setattr(s.collections[0], "name", "VPC 2"),
        lambda s: setattr(s.services[0], "usage_quantity", Decimal("372")),
        lambda s: setattr(s.services[0], "pricing_term", "reserved_1yr"),
        lambda s: setattr(s.connectors[0], "arrow_style", "two_way"),
        lambda s: s.services.pop(),
    ]
    for change in changes:
        other = base.model_copy(deep=True)
        change(other)
        assert fingerprint(other) != fingerprint(base)


def test_quantities_compare_at_the_stored_scale():
    base = state_of(_architecture())
    other = base.model_copy(deep=True)
    other.services[0].usage_quantity = Decimal("744.00000")
    assert fingerprint(other) == fingerprint(base)


def test_public_or_private_is_not_content():
    architecture = _architecture()
    before = fingerprint(state_of(architecture))
    architecture.is_public = True
    assert fingerprint(state_of(architecture)) == before


def test_transient_graph_holds_the_state():
    state = state_of(_architecture())
    graph = to_transient(state)
    assert state_of_transient(graph) == {c.id for c in state.collections}
    connector = graph.connectors[0]
    assert connector.sku_selection is not None and connector.sku_selection.sku == "DT"


def state_of_transient(graph: Architecture) -> set:
    for c in graph.collections:
        c.deleted_at = None
        c.created_at = T0
    return {c.id for c in graph.collections}
