"""Unit tests for the price calculation service (spec FR-011, FR-012, FR-017;
004-canvas-pricing-improvements FR-001-FR-005).

Pure logic tests: constructs in-memory ORM objects (never persisted) and monkeypatches the
DuckDB price/unit lookups, so these run without a database or the real Parquet data.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.models.orm import Architecture, Collection, DataConnector, SKUSelection
from src.models.schemas import CalculationDuration
from src.pricing_data.pricing import ReservedPrice
from src.services import price_calculation

# 018-app-cloud-deployment: price calculation takes one snapshot (date and revision) per request.
FAKE_SNAPSHOT = SimpleNamespace(snapshot_date="2026-01-01", revision=1)


def _patch_on_demand_price(monkeypatch, lookup):
    """019 (T024/T025): on-demand prices now come from the AWS adapter as tiers. Serve what the
    old `lookup_price` mock returned as one open tier (or nothing), so every expected value is
    unchanged."""
    from src.pricing_data.providers import aws
    from src.pricing_data.providers.base import Tier

    def fake_tiers(**kwargs):
        price = lookup(**kwargs)
        return [] if price is None else [Tier(Decimal(0), Decimal(str(price)), None)]

    monkeypatch.setattr(aws, "lookup_price_tiers", fake_tiers)


def _selection(**kwargs) -> SKUSelection:
    # These ORM objects are never persisted in these unit tests, so the mapped column default
    # for `id` (applied at INSERT time) never fires — set it explicitly, matching what a real
    # committed-and-refreshed selection always has.
    defaults = {
        "id": uuid.uuid4(),
        "service_code": "AmazonEC2",
        "sku": "SKU1",
        "pricing_term": "on_demand",
        "purchase_option": "not_applicable",
        "usage_quantity": Decimal("10"),
    }
    defaults.update(kwargs)
    s = SKUSelection(**defaults)
    return s


def _mock_no_period_units(monkeypatch):
    """These pre-004 tests are about summing/warnings, not proration — mock every selection's
    unit as a recognized `no_period` one ("Hrs") and pair with duration=1_day (multiplier=1,
    see below) so `raw_cost` passes through unchanged, preserving their original expected
    totals exactly."""

    def fake_resolve_units(selections, *, region=None, snapshot=None):
        return dict.fromkeys(selections, "Hrs")

    # 019 (T045): units are resolved through the AWS adapter.
    from src.pricing_data.providers import aws

    monkeypatch.setattr(aws, "resolve_units", fake_resolve_units)


def test_sums_priceable_line_items(monkeypatch):
    _patch_on_demand_price(monkeypatch, lambda **kw: 2.5)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_no_period_units(monkeypatch)

    collection = Collection(type="application_component", name="Web", region="us-east-1")
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
    _patch_on_demand_price(monkeypatch, lambda **kw: None)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_no_period_units(monkeypatch)

    collection = Collection(type="application_component", name="Web", region="us-east-1")
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
    _patch_on_demand_price(monkeypatch, lambda **kw: 1.0)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_no_period_units(monkeypatch)

    coll_a = Collection(id=uuid.uuid4(), type="vpc", name="VPC A", region="us-east-1")
    coll_a.sku_selections = []
    coll_b = Collection(id=uuid.uuid4(), type="vpc", name="VPC B", region="us-east-1")
    coll_b.sku_selections = []
    architecture = Architecture(name="A")
    architecture.collections = [coll_a, coll_b]
    connector = DataConnector(from_collection_id=coll_a.id, to_collection_id=coll_b.id)
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
    _patch_on_demand_price(monkeypatch, lambda **kw: 1.0)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_no_period_units(monkeypatch)

    architecture = Architecture(name="A")
    vpcs = [
        Collection(id=uuid.uuid4(), type="vpc", name=f"VPC{i}", region="us-east-1")
        for i in range(vpc_count)
    ]
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
    _patch_on_demand_price(monkeypatch, lambda **kw: 2.5)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_no_period_units(monkeypatch)

    def build(nested: bool) -> Architecture:
        vpc = Collection(id=uuid.uuid4(), type="vpc", name="VPC", region="us-east-1")
        vpc.sku_selections = []
        app = Collection(
            id=uuid.uuid4(), type="application_component", name="App", region="us-east-1"
        )
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
    def fake_resolve_units(selections, *, region=None, snapshot=None):
        return {(sku, term, purchase): unit_by_sku.get(sku) for sku, term, purchase in selections}

    # 019 (T045): units are resolved through the AWS adapter.
    from src.pricing_data.providers import aws

    monkeypatch.setattr(aws, "resolve_units", fake_resolve_units)


def _architecture_with(selection: SKUSelection) -> Architecture:
    collection = Collection(type="application_component", name="Web", region="us-east-1")
    collection.sku_selections = [selection]
    architecture = Architecture(name="A")
    architecture.collections = [collection]
    architecture.connectors = []
    return architecture


# --- 006-fix-reserved-pricing: Reserved-term calculation correctness (FR-001-FR-005) ---
#
# These replace 004's `test_reserved_1yr_prorates_against_term_length`/
# `test_reserved_3yr_prorates_against_term_length`, which asserted the exact bug this feature
# fixes (a Reserved total silently divided by the term length as if `usage_quantity` were a
# term-long quantity). `lookup_reserved_price` — not `lookup_price` — is now the Reserved path's
# only pricing lookup.


def _mock_reserved_price(monkeypatch, result: ReservedPrice | None):
    # 019 (T045): the Reserved lookup is reached through the AWS adapter.
    from src.pricing_data.providers import aws

    monkeypatch.setattr(aws, "lookup_reserved_price", lambda **kw: result)


def test_reserved_no_upfront_recurring_cost_ignores_usage_quantity(monkeypatch):
    """FR-001: a Reserved/No-Upfront selection's cost is `recurring_rate * 24 *
    duration_days` — `usage_quantity` plays no role at all, however it's set (006,
    Clarifications)."""
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_reserved_price(monkeypatch, ReservedPrice(recurring_rate=1.0, upfront_fee=None))

    selection = _selection(
        pricing_term="reserved_1yr",
        purchase_option="no_upfront",
        usage_quantity=Decimal("999"),  # deliberately absurd — must be irrelevant
    )
    architecture = _architecture_with(selection)

    one_day = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_day
    )
    one_month = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )
    one_year = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_year
    )

    assert one_day.total_price == Decimal("24")
    assert one_month.total_price == Decimal("744")  # 1.0 * 24 * 31
    assert one_year.total_price == Decimal("8760")  # 1.0 * 24 * 365


def test_reserved_missing_recurring_rate_is_unpriceable(monkeypatch):
    """FR-005: a row exists (so `lookup_reserved_price` doesn't return None outright) but with
    no `Hrs` row — excluded with a reason, never guessed."""
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_reserved_price(monkeypatch, ReservedPrice(recurring_rate=None, upfront_fee=None))

    selection = _selection(pricing_term="reserved_1yr", purchase_option="no_upfront")
    architecture = _architecture_with(selection)

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )

    assert result.total_price == Decimal("0")
    assert len(result.unpriceable) == 1
    assert "recurring rate" in result.unpriceable[0].reason
    assert result.line_items[0].priceable is False


def test_reserved_no_lookup_result_at_all_is_unpriceable(monkeypatch):
    """FR-005: `lookup_reserved_price` returning `None` outright (no matching row whatsoever)
    is unpriceable too, not a crash."""
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_reserved_price(monkeypatch, None)

    selection = _selection(pricing_term="reserved_1yr", purchase_option="no_upfront")
    architecture = _architecture_with(selection)

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )

    assert result.total_price == Decimal("0")
    assert len(result.unpriceable) == 1
    assert result.line_items[0].priceable is False


def test_reserved_partial_upfront_includes_amortized_upfront_share(monkeypatch):
    """FR-002: total = recurring contribution + `upfront_fee * duration_days / term_days`."""
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_reserved_price(monkeypatch, ReservedPrice(recurring_rate=1.0, upfront_fee=365.0))

    selection = _selection(pricing_term="reserved_1yr", purchase_option="partial_upfront")
    architecture = _architecture_with(selection)

    one_month = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )

    # recurring: 1.0 * 24 * 31 = 744; upfront: 365 * 31 / 365 = 31; total = 775.
    assert one_month.total_price == Decimal("775")


def test_reserved_all_upfront_zero_recurring_never_zeroes_the_total(monkeypatch):
    """Edge Case: an All-Upfront selection's $0/hr recurring rate must not zero out the total
    — the upfront share still applies."""
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_reserved_price(monkeypatch, ReservedPrice(recurring_rate=0.0, upfront_fee=365.0))

    selection = _selection(pricing_term="reserved_1yr", purchase_option="all_upfront")
    architecture = _architecture_with(selection)

    one_month = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )

    assert one_month.total_price == Decimal("31")  # 365 * 31 / 365
    assert one_month.total_price != Decimal("0")


def test_reserved_no_upfront_gets_no_upfront_contribution(monkeypatch):
    """FR-003: even if `lookup_reserved_price` somehow returned an `upfront_fee` for a
    No-Upfront selection (shouldn't happen in real data, but the branch must not read it
    either way), the total stays exactly the recurring-only contribution."""
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_reserved_price(monkeypatch, ReservedPrice(recurring_rate=1.0, upfront_fee=999999.0))

    selection = _selection(pricing_term="reserved_1yr", purchase_option="no_upfront")
    architecture = _architecture_with(selection)

    one_month = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )

    assert one_month.total_price == Decimal("744")  # 1.0 * 24 * 31, upfront_fee ignored


def test_reserved_partial_upfront_missing_upfront_fee_is_unpriceable(monkeypatch):
    """FR-005: the recurring rate is present but the upfront row is missing for a
    Partial/All-Upfront selection — excluded with a reason distinct from the
    missing-recurring-rate case."""
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_reserved_price(monkeypatch, ReservedPrice(recurring_rate=1.0, upfront_fee=None))

    selection = _selection(pricing_term="reserved_1yr", purchase_option="partial_upfront")
    architecture = _architecture_with(selection)

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )

    assert result.total_price == Decimal("0")
    assert len(result.unpriceable) == 1
    assert "upfront fee" in result.unpriceable[0].reason
    assert result.line_items[0].priceable is False


def test_reserved_3yr_amortizes_upfront_against_1095_days(monkeypatch):
    """FR-002: a 3-Year Reserved selection's upfront share is prorated against 1095 days, not
    365."""
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_reserved_price(monkeypatch, ReservedPrice(recurring_rate=0.0, upfront_fee=1095.0))

    selection = _selection(pricing_term="reserved_3yr", purchase_option="all_upfront")
    architecture = _architecture_with(selection)

    one_month = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )

    assert one_month.total_price == Decimal("31")  # 1095 * 31 / 1095


def test_on_demand_calculation_unchanged_by_reserved_fix(monkeypatch):
    """SC-003: restructuring the Reserved branch (006) must not alter On-Demand's own math —
    same scenario/expected value as `test_on_demand_no_period_unit_scales_by_duration_days`,
    asserted again here explicitly as this fix's regression check."""
    _patch_on_demand_price(monkeypatch, lambda **kw: 2.0)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_units(monkeypatch, {"SKU1": "Requests"})

    selection = _selection(usage_quantity=Decimal("10"))
    architecture = _architecture_with(selection)

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )

    assert result.total_price == Decimal("620")


def test_on_demand_no_period_unit_scales_by_duration_days(monkeypatch):
    """FR-003: an on-demand Hrs-family selection's quantity is a steady daily rate — scaled
    directly by the selected duration's day-count."""
    _patch_on_demand_price(monkeypatch, lambda **kw: 2.0)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
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
    _patch_on_demand_price(monkeypatch, lambda **kw: 3.1)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
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
    _patch_on_demand_price(monkeypatch, lambda **kw: 5.0)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
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
    _patch_on_demand_price(monkeypatch, lambda **kw: 1.0)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_units(monkeypatch, {"SKU1": "Hrs"})

    architecture = _architecture_with(_selection())

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_year
    )

    assert result.duration == CalculationDuration.one_year


def test_default_duration_is_one_month(monkeypatch):
    _patch_on_demand_price(monkeypatch, lambda **kw: 1.0)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_units(monkeypatch, {"SKU1": "Hrs"})

    architecture = _architecture_with(_selection())

    result = price_calculation.calculate_architecture_price(architecture)

    assert result.duration == CalculationDuration.one_month


# --- 004-canvas-pricing-improvements: warnings/exclusions name their component(s) ---
# (FR-012, FR-013)


def test_unpriceable_collection_selection_names_its_collection(monkeypatch):
    _patch_on_demand_price(monkeypatch, lambda **kw: None)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_no_period_units(monkeypatch)

    collection = Collection(type="application_component", name="Web Tier", region="us-east-1")
    collection.sku_selections = [_selection()]
    architecture = Architecture(name="A")
    architecture.collections = [collection]
    architecture.connectors = []

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_day
    )

    assert result.unpriceable[0].components == ["Web Tier"]


def test_unpriceable_connector_selection_names_its_two_collections(monkeypatch):
    _patch_on_demand_price(monkeypatch, lambda **kw: None)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_no_period_units(monkeypatch)

    coll_a = Collection(id=uuid.uuid4(), type="vpc", name="VPC A", region="us-east-1")
    coll_a.sku_selections = []
    coll_b = Collection(id=uuid.uuid4(), type="vpc", name="VPC B", region="us-east-1")
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
    _patch_on_demand_price(monkeypatch, lambda **kw: 5.0)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_units(monkeypatch, {"SKU1": "Quantity"})

    collection = Collection(type="application_component", name="Odd Billing", region="us-east-1")
    collection.sku_selections = [_selection()]
    architecture = Architecture(name="A")
    architecture.collections = [collection]
    architecture.connectors = []

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )

    assert result.unpriceable[0].components == ["Odd Billing"]


# --- 010-multi-region-support: PriceLineItem.region resolution (data-model.md, research.md §11) --


def test_collection_owned_line_item_gets_its_collections_region(monkeypatch):
    _patch_on_demand_price(monkeypatch, lambda **kw: 2.5)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_no_period_units(monkeypatch)

    collection = Collection(
        id=uuid.uuid4(), type="application_component", name="Web", region="eu-west-1"
    )
    collection.sku_selections = [_selection()]
    architecture = Architecture(name="A")
    architecture.collections = [collection]
    architecture.connectors = []

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_day
    )

    assert result.line_items[0].region == "eu-west-1"


def test_connector_owned_line_item_gets_its_from_collections_region(monkeypatch):
    """spec FR-006/data-model.md: a Connector's own line item is attributed to its "from"
    Collection's region, never its "to" Collection's."""
    _patch_on_demand_price(monkeypatch, lambda **kw: 1.0)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_no_period_units(monkeypatch)

    coll_a = Collection(id=uuid.uuid4(), type="vpc", name="VPC A", region="us-west-2")
    coll_a.sku_selections = []
    coll_b = Collection(id=uuid.uuid4(), type="vpc", name="VPC B", region="ap-northeast-1")
    coll_b.sku_selections = []
    connector = DataConnector(from_collection_id=coll_a.id, to_collection_id=coll_b.id)
    connector.sku_selection = _selection(usage_quantity=Decimal("5"))
    architecture = Architecture(name="A")
    architecture.collections = [coll_a, coll_b]
    architecture.connectors = [connector]

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_day
    )

    assert result.line_items[0].region == "us-west-2"


def test_line_item_region_defaults_to_none_when_ownership_unresolvable(monkeypatch):
    """Defensive fallback (data-model.md, research.md §11): expected unreachable in normal
    operation (Collection.region is NOT NULL in the database), but a transient, never-persisted
    Collection with no `region` set at all — exactly `build_transient_architecture`'s synthetic
    snapshot-calculation Collection — must still resolve to `region=None` rather than raising,
    so the frontend's "Global" fallback grouping (FR-015) has a defined contract to render."""
    _patch_on_demand_price(monkeypatch, lambda **kw: 2.5)
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    _mock_no_period_units(monkeypatch)

    # Never given a `region=` kwarg, unlike every other test in this file — simulates
    # `build_transient_architecture`'s throwaway Collection.
    collection = Collection(type="application_component", name="Snapshot")
    collection.sku_selections = [_selection()]
    architecture = Architecture(name="A")
    architecture.collections = [collection]
    architecture.connectors = []

    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_day
    )

    assert result.line_items[0].region is None


# --- 019-gcp-azure-providers-trends: AWS graduated tiers (research R8, FR-008, T013) --------
# These use the real AWS fixture (tests/fixtures/pricing_parquet/aws/README.md), not mocks.

EGRESS_SKU = "5M4327XEUKBBTWAT"  # us-west-2 internet egress: 0.09, 0.085, 0.07, 0.05 per GB


def _real_architecture(region: str, **selection) -> Architecture:
    collection = Collection(type="application_component", name="Web", region=region)
    collection.sku_selections = [_selection(**selection)]
    architecture = Architecture(name="A", provider="aws")
    architecture.collections = [collection]
    architecture.connectors = []
    return architecture


def test_aws_egress_is_priced_across_its_tiers():
    # 20,480 GB in a month, entered as a daily amount (no-period unit "GB").
    architecture = _real_architecture(
        "us-west-2", service_code="AWSDataTransfer", sku=EGRESS_SKU,
        usage_quantity=Decimal(20480) / Decimal(31),
    )
    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )
    line = result.line_items[0]
    assert line.priceable is True
    assert line.price.quantize(Decimal("0.01")) == Decimal("1792.00")  # 10240×0.09 + 10240×0.085
    assert [(p.rate, p.quantity.quantize(Decimal("0.01"))) for p in line.tiers] == [
        (Decimal("0.09"), Decimal("10240.00")),
        (Decimal("0.085"), Decimal("10240.00")),
    ]
    assert sum(p.cost for p in line.tiers) == line.price


def test_a_non_tiered_aws_sku_costs_the_same_as_before():
    from src.pricing_data.pricing import lookup_price

    architecture = _real_architecture(
        "us-east-1", sku="NN4EGUUQRWVYP98C", usage_quantity=Decimal(24)  # t3.medium, 24 h/day
    )
    result = price_calculation.calculate_architecture_price(
        architecture, duration=CalculationDuration.one_month
    )
    old = lookup_price(sku="NN4EGUUQRWVYP98C", pricing_term="on_demand",
                       purchase_option="not_applicable", region="us-east-1")
    assert result.line_items[0].price == Decimal(str(old)) * 24 * 31
    assert result.line_items[0].tiers is None  # contracts §5: null when not tiered
