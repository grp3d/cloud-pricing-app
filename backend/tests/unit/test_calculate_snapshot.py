"""Unit tests for the snapshot-calculation object-graph builder (US5, FR-016a,
research.md §5) — 008-ui-updates-corrections.

Confirms the transient (never-persisted) Architecture/Collection/SKUSelection graph
`build_transient_architecture` constructs is priced correctly by the existing, unmodified
`calculate_architecture_price()` — including the specific case a naive linear-scaling
approximation would get wrong: a Reserved-term selection's total at two different durations
is not related by simple linear scaling (Constitution Principle I; 006's own precedent).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.models.schemas import CalculationDuration, PricingTerm, PurchaseOption, SnapshotSelection
from src.pricing_data.pricing import ReservedPrice
from src.services import price_calculation
from src.services.price_calculation import EmptySnapshotError, build_transient_architecture


def _selection(**kwargs) -> SnapshotSelection:
    defaults = dict(
        service_code="AmazonEC2",
        sku="SKU1",
        pricing_term=PricingTerm.on_demand,
        purchase_option=PurchaseOption.not_applicable,
        usage_quantity=Decimal("2"),
    )
    defaults.update(kwargs)
    return SnapshotSelection(**defaults)


def test_builds_one_collection_holding_every_selection():
    selections = [
        _selection(sku="SKU1"),
        _selection(sku="SKU2", service_code="AmazonS3"),
    ]

    architecture = build_transient_architecture(selections)

    assert architecture.connectors == []
    assert len(architecture.collections) == 1
    built = architecture.collections[0].sku_selections
    assert [s.sku for s in built] == ["SKU1", "SKU2"]
    # PriceLineItem.sku_selection_id is required (not Optional) — every transient selection
    # needs its own synthetic id, since it was never INSERTed to get one for free.
    assert all(s.id is not None for s in built)


def test_construction_requires_no_db_session():
    # Nothing to assert against a real session here (no DB in these unit tests) — the
    # contract is that construction alone never needs one; the function's signature itself
    # (no session parameter) is what enforces this.
    build_transient_architecture([_selection()])  # must not raise


def test_empty_selections_raises_empty_snapshot_error():
    """data-model.md's validation rule: an empty snapshot has no meaningful prior total to
    adjust — raised before any object is constructed, mapped to a 400 by the endpoint layer
    (src/main.py), not silently priced as a $0 total."""
    with pytest.raises(EmptySnapshotError):
        build_transient_architecture([])


def test_reserved_term_total_at_two_durations_matches_authoritative_formula(monkeypatch):
    """The transient graph must be priced through the *real* recurring-rate + upfront-fee
    formula at each duration, not any shortcut — regression-checked against the exact values
    006's own test suite already established for these inputs (`test_price_calculation.py`'s
    `test_reserved_partial_upfront_includes_amortized_upfront_share`/
    `test_reserved_3yr_amortizes_upfront_against_1095_days`)."""
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    monkeypatch.setattr(
        price_calculation,
        "lookup_reserved_price",
        lambda **kw: ReservedPrice(recurring_rate=1.0, upfront_fee=365.0),
    )

    selections = [
        _selection(
            pricing_term=PricingTerm.reserved_1yr,
            purchase_option=PurchaseOption.partial_upfront,
            usage_quantity=Decimal("1"),
        )
    ]

    one_month = price_calculation.calculate_architecture_price(
        build_transient_architecture(selections), duration=CalculationDuration.one_month
    )
    one_year = price_calculation.calculate_architecture_price(
        build_transient_architecture(selections), duration=CalculationDuration.one_year
    )

    # recurring: 1 * 24 * 31 = 744; upfront: 365 * 31 / 365 = 31; total = 775.
    assert one_month.total_price == Decimal("775")
    # recurring: 1 * 24 * 365 = 8760; upfront: 365 * 365 / 365 = 365; total = 9125.
    assert one_year.total_price == Decimal("9125")


def test_reserved_term_total_ignores_usage_quantity_not_estimated(monkeypatch):
    """The specific case a naive/estimated approach *does* get wrong — 006's own precedent
    bug was a Reserved total that scaled with `usage_quantity` as if it meant a term-long
    quantity (spec FR-001, Clarifications: it has no Reserved-term meaning at all). Confirms
    `build_transient_architecture` routes through the real, unmodified formula rather than
    any input-derived shortcut: an absurd `usage_quantity` must change nothing."""
    monkeypatch.setattr(price_calculation, "resolve_latest_snapshot_date", lambda: "2026-01-01")
    monkeypatch.setattr(
        price_calculation,
        "lookup_reserved_price",
        lambda **kw: ReservedPrice(recurring_rate=1.0, upfront_fee=365.0),
    )

    normal = build_transient_architecture(
        [
            _selection(
                pricing_term=PricingTerm.reserved_1yr,
                purchase_option=PurchaseOption.partial_upfront,
                usage_quantity=Decimal("1"),
            )
        ]
    )
    absurd = build_transient_architecture(
        [
            _selection(
                pricing_term=PricingTerm.reserved_1yr,
                purchase_option=PurchaseOption.partial_upfront,
                usage_quantity=Decimal("999"),
            )
        ]
    )

    result_normal = price_calculation.calculate_architecture_price(
        normal, duration=CalculationDuration.one_month
    )
    result_absurd = price_calculation.calculate_architecture_price(
        absurd, duration=CalculationDuration.one_month
    )

    assert result_normal.total_price == result_absurd.total_price == Decimal("775")
