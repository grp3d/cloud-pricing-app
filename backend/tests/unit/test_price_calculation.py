"""Unit tests for the price calculation service (spec FR-011, FR-012, FR-017).

Pure logic tests: constructs in-memory ORM objects (never persisted) and monkeypatches the
DuckDB price lookup, so these run without a database or the real Parquet data.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from src.models.orm import Architecture, Collection, DataConnector, SKUSelection
from src.services import price_calculation


def _selection(**kwargs) -> SKUSelection:
    # These ORM objects are never persisted in these unit tests, so the mapped column default
    # for `id` (applied at INSERT time) never fires — set it explicitly, matching what a real
    # committed-and-refreshed selection always has.
    defaults = dict(
        id=uuid.uuid4(),
        service_code="AmazonEC2",
        sku="SKU1",
        pricing_term="on_demand",
        purchase_option="not_applicable",
        usage_quantity=Decimal("10"),
    )
    defaults.update(kwargs)
    s = SKUSelection(**defaults)
    return s


def test_sums_priceable_line_items(monkeypatch):
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: 2.5)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")

    collection = Collection(type="application_component", name="Web")
    collection.sku_selections = [_selection(usage_quantity=Decimal("10"))]
    architecture = Architecture(name="A")
    architecture.collections = [collection]
    architecture.connectors = []

    result = price_calculation.calculate_architecture_price(architecture)

    assert result.total_price == Decimal("25.0")
    assert result.line_items[0].priceable is True
    assert result.unpriceable == []


def test_unpriceable_sku_excluded_from_total_not_estimated(monkeypatch):
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: None)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")

    collection = Collection(type="application_component", name="Web")
    collection.sku_selections = [_selection()]
    architecture = Architecture(name="A")
    architecture.collections = [collection]
    architecture.connectors = []

    result = price_calculation.calculate_architecture_price(architecture)

    assert result.total_price == Decimal("0")
    assert len(result.unpriceable) == 1
    assert result.line_items[0].priceable is False
    assert result.line_items[0].price is None


def test_connector_attached_sku_included_in_total(monkeypatch):
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: 1.0)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")

    architecture = Architecture(name="A")
    architecture.collections = []
    connector = DataConnector()
    connector.sku_selection = _selection(usage_quantity=Decimal("5"))
    architecture.connectors = [connector]

    result = price_calculation.calculate_architecture_price(architecture)

    assert result.total_price == Decimal("5.0")


@pytest.mark.parametrize("vpc_count,connected,expect_warning", [(1, False, False), (2, False, True), (2, True, False)])
def test_unconnected_vpc_warning(monkeypatch, vpc_count, connected, expect_warning):
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: 1.0)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")

    import uuid

    architecture = Architecture(name="A")
    vpcs = [Collection(id=uuid.uuid4(), type="vpc", name=f"VPC{i}") for i in range(vpc_count)]
    for v in vpcs:
        v.sku_selections = []
    architecture.collections = vpcs
    architecture.connectors = []
    if connected and vpc_count == 2:
        connector = DataConnector(from_collection_id=vpcs[0].id, to_collection_id=vpcs[1].id)
        connector.sku_selection = None
        architecture.connectors = [connector]

    result = price_calculation.calculate_architecture_price(architecture)

    warning_codes = [w.code for w in result.warnings]
    if expect_warning:
        assert "unconnected_vpcs" in warning_codes
    else:
        assert "unconnected_vpcs" not in warning_codes
