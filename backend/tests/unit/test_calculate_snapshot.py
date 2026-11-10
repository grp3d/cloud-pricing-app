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
from types import SimpleNamespace

import pytest

from src.models.schemas import (
    CalculationDuration,
    PricingTerm,
    PurchaseOption,
    SnapshotSelection,
)
from src.pricing_data.pricing import ReservedPrice
from src.pricing_data.providers import aws
from src.services import price_calculation
from src.services.price_calculation import (
    EmptySnapshotError,
    build_transient_architecture,
)

# 018-app-cloud-deployment: price calculation takes one snapshot (date and revision) per request.
FAKE_SNAPSHOT = SimpleNamespace(snapshot_date="2026-01-01", revision=1)


def _selection(**kwargs) -> SnapshotSelection:
    defaults = {
        "service_code": "AmazonEC2",
        "sku": "SKU1",
        "pricing_term": PricingTerm.on_demand,
        "purchase_option": PurchaseOption.not_applicable,
        "usage_quantity": Decimal("2"),
    }
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
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    monkeypatch.setattr(
        aws,  # 019 (T045): reached through the AWS adapter
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
    monkeypatch.setattr(price_calculation, "get_active_snapshot", lambda *_: FAKE_SNAPSHOT)
    monkeypatch.setattr(
        aws,  # 019 (T045): reached through the AWS adapter
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


def test_transient_collection_uses_the_configured_pricing_region(monkeypatch):
    """016-canvas-icon-layout, FR-025: the snapshot collection's region comes from
    `AWS_PRICING_REGION`, not a hard-coded value."""
    monkeypatch.setattr(price_calculation.settings, "aws_pricing_region", "eu-west-1")
    architecture = build_transient_architecture([_selection()])
    assert architecture.collections[0].region == "eu-west-1"


# --- 020 (T002, research R2, data-model §2): provider, regions and options -------------------

GCP_OPTIONS = {"kind": "gcp_machine", "version": 1, "vcpus": 4, "memory_gib": "16",
               "ram_sku": "5B01-D157-A097"}


def test_transient_architecture_takes_the_requested_provider():
    assert build_transient_architecture([_selection()], provider="gcp").provider == "gcp"


def test_transient_architecture_defaults_to_aws_without_a_provider():
    assert build_transient_architecture([_selection()]).provider == "aws"
    assert build_transient_architecture([_selection()], provider=None).provider == "aws"


def test_selections_are_grouped_into_one_collection_per_region():
    architecture = build_transient_architecture(
        [
            _selection(sku="A", region="us-east1"),
            _selection(sku="B", region="europe-west1"),
            _selection(sku="C", region="us-east1"),
        ],
        provider="gcp",
    )
    by_region = {c.region: [s.sku for s in c.sku_selections] for c in architecture.collections}
    assert by_region == {"us-east1": ["A", "C"], "europe-west1": ["B"]}
    for collection in architecture.collections:
        assert all(s.collection_id == collection.id for s in collection.sku_selections)


def test_a_missing_or_null_region_uses_the_configured_pricing_region(monkeypatch):
    monkeypatch.setattr(price_calculation.settings, "aws_pricing_region", "eu-west-1")
    architecture = build_transient_architecture(
        [_selection(sku="A"), _selection(sku="B", region=None), _selection(sku="C",
                                                                           region="us-west-2")]
    )
    by_region = {c.region: [s.sku for s in c.sku_selections] for c in architecture.collections}
    assert by_region == {"eu-west-1": ["A", "B"], "us-west-2": ["C"]}


def test_provider_options_are_copied_onto_each_selection_as_a_plain_dict():
    architecture = build_transient_architecture(
        [
            _selection(sku="CORE", region="us-east1", provider_options=GCP_OPTIONS),
            _selection(sku="DISK", region="us-east1"),
        ],
        provider="gcp",
    )
    built = {s.sku: s for s in architecture.collections[0].sku_selections}
    options = built["CORE"].provider_options
    assert isinstance(options, dict)
    assert options["kind"] == "gcp_machine"
    assert options["vcpus"] == 4
    assert Decimal(str(options["memory_gib"])) == Decimal("16")
    assert options["ram_sku"] == "5B01-D157-A097"
    assert built["DISK"].provider_options is None


def test_empty_selections_still_raise_with_a_provider():
    with pytest.raises(EmptySnapshotError):
        build_transient_architecture([], provider="azure")
