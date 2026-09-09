"""Unit tests for the price calculation service (spec FR-011, FR-012, FR-017;
004-canvas-pricing-improvements FR-001-FR-005).

Pure logic tests: constructs in-memory ORM objects (never persisted) and monkeypatches the
DuckDB price/unit lookups, so these run without a database or the real Parquet data.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from src.models.orm import Architecture, Collection, DataConnector, SKUSelection
from src.models.schemas import CalculationDuration
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


def _mock_no_period_units(monkeypatch):
    """These pre-004 tests are about summing/warnings, not proration — mock every selection's
    unit as a recognized `no_period` one ("Hrs") and pair with duration=1_day (multiplier=1,
    see below) so `raw_cost` passes through unchanged, preserving their original expected
    totals exactly."""

    def fake_resolve_units(selections, *, snapshot_date=None):
        return {key: "Hrs" for key in selections}

    monkeypatch.setattr(price_calculation, "resolve_units", fake_resolve_units)


def test_sums_priceable_line_items(monkeypatch):
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: 2.5)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    _mock_no_period_units(monkeypatch)

    collection = Collection(type="application_component", name="Web")
    collection.sku_selections = [_selection(usage_quantity=Decimal("10"), sku="Hrs-sku")]
    architecture = Architecture(name="A")
    architecture.collections = [collection]
    architecture.connectors = []

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_day
    )

    assert result.total_price == Decimal("25.0")
    assert result.line_items[0].priceable is True
    assert result.unpriceable == []


def test_unpriceable_sku_excluded_from_total_not_estimated(monkeypatch):
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: None)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    _mock_no_period_units(monkeypatch)

    collection = Collection(type="application_component", name="Web")
    collection.sku_selections = [_selection()]
    architecture = Architecture(name="A")
    architecture.collections = [collection]
    architecture.connectors = []

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_day
    )

    assert result.total_price == Decimal("0")
    assert len(result.unpriceable) == 1
    assert result.line_items[0].priceable is False
    assert result.line_items[0].price is None


def test_connector_attached_sku_included_in_total(monkeypatch):
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: 1.0)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    _mock_no_period_units(monkeypatch)

    architecture = Architecture(name="A")
    architecture.collections = []
    connector = DataConnector()
    connector.sku_selection = _selection(usage_quantity=Decimal("5"))
    architecture.connectors = [connector]

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_day
    )

    assert result.total_price == Decimal("5.0")


@pytest.mark.parametrize(
    "vpc_count,connected,expect_warning", [(1, False, False), (2, False, True), (2, True, False)]
)
def test_unconnected_vpc_warning(monkeypatch, vpc_count, connected, expect_warning):
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: 1.0)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    _mock_no_period_units(monkeypatch)

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

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_day
    )

    warning_codes = [w.code for w in result.warnings]
    if expect_warning:
        assert "unconnected_vpcs" in warning_codes
    else:
        assert "unconnected_vpcs" not in warning_codes


def test_nesting_does_not_affect_total(monkeypatch):
    """002-vpc-component-nesting FR-009: nesting an Application Component inside a VPC must
    not change the calculated total — price_calculation.py sums every Collection in
    architecture.collections regardless of parent_collection_id, so nested vs. top-level must
    produce an identical result.
    """
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: 2.5)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    _mock_no_period_units(monkeypatch)

    def build(nested: bool) -> Architecture:
        vpc = Collection(id=uuid.uuid4(), type="vpc", name="VPC")
        vpc.sku_selections = []
        app = Collection(id=uuid.uuid4(), type="application_component", name="App")
        app.sku_selections = [_selection(usage_quantity=Decimal("10"))]
        if nested:
            app.parent_collection_id = vpc.id
        architecture = Architecture(name="A")
        architecture.collections = [vpc, app]
        architecture.connectors = []
        return architecture

    top_level_result = price_calculation.calculate_architecture_price(
        build(nested=False), duration=CalculationDuration.one_day
    )
    nested_result = price_calculation.calculate_architecture_price(
        build(nested=True), duration=CalculationDuration.one_day
    )

    assert top_level_result.total_price == nested_result.total_price == Decimal("25.0")


# --- 004-canvas-pricing-improvements: duration-proration math (FR-002, FR-003, FR-004, FR-005) --


def _mock_units(monkeypatch, unit_by_sku: dict[str, str]):
    def fake_resolve_units(selections, *, snapshot_date=None):
        return {(sku, term, purchase): unit_by_sku.get(sku) for sku, term, purchase in selections}

    monkeypatch.setattr(price_calculation, "resolve_units", fake_resolve_units)


def _architecture_with(selection: SKUSelection) -> Architecture:
    collection = Collection(type="application_component", name="Web")
    collection.sku_selections = [selection]
    architecture = Architecture(name="A")
    architecture.collections = [collection]
    architecture.connectors = []
    return architecture


def test_reserved_1yr_prorates_against_term_length(monkeypatch):
    """FR-002: a Reserved commitment's raw cost covers the full term — divided by 365 for a
    1-day view, unchanged for a 1-year view."""
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: 365.0)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    _mock_units(monkeypatch, {"SKU1": "Hrs"})

    selection = _selection(pricing_term="reserved_1yr", usage_quantity=Decimal("1"))
    architecture = _architecture_with(selection)

    one_day = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_day
    )
    one_year = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_year
    )

    assert one_day.total_price == Decimal("1")
    assert one_year.total_price == Decimal("365")


def test_reserved_3yr_prorates_against_term_length(monkeypatch):
    """FR-002: a 3-year commitment's term is 1095 days."""
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: 1095.0)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    _mock_units(monkeypatch, {"SKU1": "Hrs"})

    selection = _selection(pricing_term="reserved_3yr", usage_quantity=Decimal("1"))
    architecture = _architecture_with(selection)

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )

    assert result.total_price == Decimal("31")


def test_on_demand_no_period_unit_scales_by_duration_days(monkeypatch):
    """FR-003: an on-demand Hrs-family selection's quantity is a steady daily rate — scaled
    directly by the selected duration's day-count."""
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: 2.0)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    _mock_units(monkeypatch, {"SKU1": "Requests"})

    selection = _selection(usage_quantity=Decimal("10"))
    architecture = _architecture_with(selection)

    one_day = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_day
    )
    one_month = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )

    assert one_day.total_price == Decimal("20")
    assert one_month.total_price == Decimal("620")


def test_on_demand_fixed_period_unit_scales_between_periods(monkeypatch):
    """FR-004: an on-demand GB-Mo-family selection's raw cost already covers one month — scaled
    between that period and the selected duration, not treated as a daily rate."""
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: 3.1)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    _mock_units(monkeypatch, {"SKU1": "GB-Mo"})

    selection = _selection(usage_quantity=Decimal("10"))
    architecture = _architecture_with(selection)

    one_month = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )
    one_year = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_year
    )

    # raw_cost = 3.1 * 10 = 31; one_month duration_days(31) / period_days(31) == 1 -> unchanged.
    assert one_month.total_price == Decimal("31")
    # one_year: 31 * 365 / 31 == 365.
    assert one_year.total_price == Decimal("365")


def test_on_demand_unrecognized_unit_excluded_not_guessed(monkeypatch):
    """FR-005: a billing unit outside the recognized tables is excluded from the total and
    listed, never included unscaled or guessed."""
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: 5.0)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    _mock_units(monkeypatch, {"SKU1": "Quantity"})

    selection = _selection(usage_quantity=Decimal("10"))
    architecture = _architecture_with(selection)

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )

    assert result.total_price == Decimal("0")
    assert len(result.unpriceable) == 1
    assert "isn't recognized as time-based" in result.unpriceable[0].reason
    assert result.line_items[0].priceable is False


def test_calculation_result_echoes_duration(monkeypatch):
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: 1.0)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    _mock_units(monkeypatch, {"SKU1": "Hrs"})

    architecture = _architecture_with(_selection())

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_year
    )

    assert result.duration == CalculationDuration.one_year


def test_default_duration_is_one_month(monkeypatch):
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: 1.0)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    _mock_units(monkeypatch, {"SKU1": "Hrs"})

    architecture = _architecture_with(_selection())

    result = price_calculation.calculate_architecture_price(architecture)

    assert result.duration == CalculationDuration.one_month


# --- 004-canvas-pricing-improvements: warnings/exclusions name their component(s) ---
# (FR-012, FR-013)


def test_unpriceable_collection_selection_names_its_collection(monkeypatch):
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: None)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    _mock_no_period_units(monkeypatch)

    collection = Collection(type="application_component", name="Web Tier")
    collection.sku_selections = [_selection()]
    architecture = Architecture(name="A")
    architecture.collections = [collection]
    architecture.connectors = []

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_day
    )

    assert result.unpriceable[0].components == ["Web Tier"]


def test_unpriceable_connector_selection_names_its_two_collections(monkeypatch):
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: None)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    _mock_no_period_units(monkeypatch)

    coll_a = Collection(id=uuid.uuid4(), type="vpc", name="VPC A")
    coll_a.sku_selections = []
    coll_b = Collection(id=uuid.uuid4(), type="vpc", name="VPC B")
    coll_b.sku_selections = []
    connector = DataConnector(from_collection_id=coll_a.id, to_collection_id=coll_b.id)
    connector.sku_selection = _selection()
    architecture = Architecture(name="A")
    architecture.collections = [coll_a, coll_b]
    architecture.connectors = [connector]

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_day
    )

    assert result.unpriceable[0].components == ["Data Connector between VPC A and VPC B"]


def test_duration_excluded_selection_also_names_its_component(monkeypatch):
    """FR-005's new exclusion case gets `components` populated the same way as the existing
    unpriceable case — both share one combined list (spec Clarifications)."""
    monkeypatch.setattr(price_calculation, "lookup_price", lambda **kw: 5.0)
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    _mock_units(monkeypatch, {"SKU1": "Quantity"})

    collection = Collection(type="application_component", name="Odd Billing")
    collection.sku_selections = [_selection()]
    architecture = Architecture(name="A")
    architecture.collections = [collection]
    architecture.connectors = []

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )

    assert result.unpriceable[0].components == ["Odd Billing"]
