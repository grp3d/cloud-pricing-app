"""Unit tests for the batched `resolve_units` billing-unit lookup
(003-service-selection-improvements, FR-004, FR-005) and for `lookup_reserved_price()`
(006-fix-reserved-pricing, FR-002, FR-004, FR-005).

Runs against the real Parquet pricing data (Constitution Principle I — no mock substitute).
"""

from __future__ import annotations

import pytest

from src.pricing_data.pricing import lookup_price, lookup_reserved_price, resolve_units

# 009-ui-fixes-next-iteration, US1, FR-001: this SKU's price_fact data has a genuine upstream
# duplicate-row anomaly — every Reserved term/purchase_option combination has two rows with two
# different prices (research.md §1), unlike KNOWN_RESERVED_SKU's clean single-row-per-combination
# data below. `lookup_price`/`lookup_reserved_price` already have deterministic "first row wins"
# semantics for exactly this situation (006's own precedent) rather than crashing or returning
# `None` — these tests lock that confirmed-working behavior in as a regression guard, without
# pinning an exact duplicate-dependent value neither duplicate row is more "correct" than the
# other.
KNOWN_DUPLICATE_ROW_SKU = "2AB37QDFJZBGQ5YP"

# Known SKUs from the real AWS pricing data (also used by tests/contract/test_sku_selections.py
# and tests/unit/test_price_calculation.py's real-data counterparts).
KNOWN_ON_DEMAND_SKU = "NN4EGUUQRWVYP98C"

# The exact SKU from the 006-fix-reserved-pricing bug report — has a clean, single row per
# (term, purchase_option, lease, unit) combination at No Upfront (verified during planning;
# unlike some other SKUs' Reserved data, it has no same-unit duplicate rows there), so it's a
# reliable fixture for asserting exact recurring_rate/upfront_fee values, not just presence.
KNOWN_RESERVED_SKU = "2THCJ54S3VW8G6VS"


def test_resolves_unit_for_a_single_sku():
    result = resolve_units(
        [(KNOWN_ON_DEMAND_SKU, "on_demand", "not_applicable")], region="us-east-1"
    )
    assert result[(KNOWN_ON_DEMAND_SKU, "on_demand", "not_applicable")] == "Hrs"


def test_resolves_units_for_multiple_skus_in_one_call():
    """Batched: multiple distinct SKUs resolved together, not one at a time."""
    other_sku = "QZ9R39S2Y8MCC9Y8"
    result = resolve_units(
        [
            (KNOWN_ON_DEMAND_SKU, "on_demand", "not_applicable"),
            (other_sku, "on_demand", "not_applicable"),
        ],
        region="us-east-1",
    )
    assert result[(KNOWN_ON_DEMAND_SKU, "on_demand", "not_applicable")] == "Hrs"
    assert result[(other_sku, "on_demand", "not_applicable")] == "Hrs"


def test_unresolvable_sku_is_none_without_failing_others():
    """A SKU with no matching price_fact row resolves to None (unpriceable, same condition as
    lookup_price) without breaking resolution for the other SKUs in the same batch."""
    result = resolve_units(
        [
            (KNOWN_ON_DEMAND_SKU, "on_demand", "not_applicable"),
            ("THIS-SKU-DOES-NOT-EXIST", "on_demand", "not_applicable"),
        ],
        region="us-east-1",
    )
    assert result[(KNOWN_ON_DEMAND_SKU, "on_demand", "not_applicable")] == "Hrs"
    assert result[("THIS-SKU-DOES-NOT-EXIST", "on_demand", "not_applicable")] is None


def test_empty_input_returns_empty_map():
    assert resolve_units([], region="us-east-1") == {}


# --- 006-fix-reserved-pricing: lookup_reserved_price() (FR-002, FR-004, FR-005) ---


def test_reserved_no_upfront_returns_recurring_rate_with_no_upfront_fee():
    """FR-003/FR-004: a No-Upfront combination has only a recurring (`Hrs`) row — `upfront_fee`
    is `None`, not `0` (there's a real difference between "no upfront cost" and "$0 upfront
    cost row present", though both happen to total the same; `None` is the honest one here
    since no `Quantity` row exists at all for No Upfront)."""
    result = lookup_reserved_price(
        sku=KNOWN_RESERVED_SKU,
        pricing_term="reserved_1yr",
        purchase_option="no_upfront",
        region="us-east-1",
    )
    assert result is not None
    assert result.recurring_rate == 12.90693
    assert result.upfront_fee is None


def test_reserved_partial_upfront_returns_both_recurring_rate_and_upfront_fee():
    """FR-002/FR-004: a Partial-Upfront combination has two distinct rows sharing every other
    column, differing only by `unit` — both values must come back, correctly matched to
    their own `unit`, not one silently standing in for the other."""
    result = lookup_reserved_price(
        sku=KNOWN_RESERVED_SKU,
        pricing_term="reserved_1yr",
        purchase_option="partial_upfront",
        region="us-east-1",
    )
    assert result is not None
    assert result.recurring_rate == 6.66161
    assert result.upfront_fee == 58356.0


def test_reserved_all_upfront_zero_recurring_rate_still_returned():
    """A $0/hr recurring rate (All Upfront) is still a real, present value — `0.0`, not
    `None` — distinguishing "priced at zero" from "no price data at all"."""
    result = lookup_reserved_price(
        sku=KNOWN_RESERVED_SKU,
        pricing_term="reserved_1yr",
        purchase_option="all_upfront",
        region="us-east-1",
    )
    assert result is not None
    assert result.recurring_rate == 0.0
    assert result.upfront_fee == 114946.0


def test_reserved_unknown_sku_returns_none():
    """FR-005: no matching row at all (any unit) — `None` outright, the same "unpriceable"
    signal `lookup_price`/`resolve_units` already use."""
    result = lookup_reserved_price(
        sku="THIS-SKU-DOES-NOT-EXIST",
        pricing_term="reserved_1yr",
        purchase_option="no_upfront",
        region="us-east-1",
    )
    assert result is None


def test_reserved_price_lookup_rejects_on_demand_term():
    """`lookup_reserved_price` is only ever meant to be called from the Reserved branch — an
    `on_demand` `pricing_term` has no lease/term to look up against, so this is a programming
    error, not a data gap; fail loudly rather than silently returning nonsense."""
    with pytest.raises(ValueError):
        lookup_reserved_price(
            sku=KNOWN_ON_DEMAND_SKU,
            pricing_term="on_demand",
            purchase_option="not_applicable",
            region="us-east-1",
        )


# --- 009-ui-fixes-next-iteration, US1: KNOWN_DUPLICATE_ROW_SKU regression (research.md §1) ---


def test_duplicate_row_sku_on_demand_still_prices():
    price = lookup_price(
        sku=KNOWN_DUPLICATE_ROW_SKU,
        pricing_term="on_demand",
        purchase_option="not_applicable",
        region="us-east-1",
    )
    assert price is not None
    assert price > 0


@pytest.mark.parametrize(
    "pricing_term,purchase_option",
    [
        ("reserved_1yr", "no_upfront"),
        ("reserved_1yr", "partial_upfront"),
        ("reserved_1yr", "all_upfront"),
        ("reserved_3yr", "no_upfront"),
        ("reserved_3yr", "partial_upfront"),
        ("reserved_3yr", "all_upfront"),
    ],
)
def test_duplicate_row_sku_every_reserved_combination_still_prices(
    pricing_term: str, purchase_option: str
):
    """Every Reserved combination for this SKU has duplicate price_fact rows (research.md §1) —
    none of them may resolve to `None`/a crash; `recurring_rate` is always present (a real
    number, `0.0` is valid for some All-Upfront rows), and `upfront_fee` is present whenever the
    purchase option isn't `no_upfront`."""
    result = lookup_reserved_price(
        sku=KNOWN_DUPLICATE_ROW_SKU,
        pricing_term=pricing_term,
        purchase_option=purchase_option,
        region="us-east-1",
    )
    assert result is not None
    assert result.recurring_rate is not None
    assert result.recurring_rate >= 0
    if purchase_option == "no_upfront":
        assert result.upfront_fee is None
    else:
        assert result.upfront_fee is not None
        assert result.upfront_fee > 0


def test_unit_matches_the_row_lookup_price_actually_prices():
    """A Reserved SKU's price_fact rows include both a recurring-rate row (unit "Hrs") and an
    upfront-quantity row (unit "Quantity") sharing the same term/lease/purchase_option — the
    resolved unit must describe whichever row `lookup_price` actually prices, not an
    arbitrary same-key row, or the displayed unit would mislabel the shown price."""
    sku = "QZ9R39S2Y8MCC9Y8"
    price = lookup_price(
        sku=sku, pricing_term="reserved_1yr", purchase_option="partial_upfront", region="us-east-1"
    )
    result = resolve_units([(sku, "reserved_1yr", "partial_upfront")], region="us-east-1")
    assert price is not None
    assert result[(sku, "reserved_1yr", "partial_upfront")] == "Hrs"
