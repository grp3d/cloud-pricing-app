"""Unit tests for the batched `resolve_units` billing-unit lookup
(003-service-selection-improvements, FR-004, FR-005).

Runs against the real Parquet pricing data (Constitution Principle I — no mock substitute).
"""

from __future__ import annotations

from src.pricing_data.pricing import lookup_price, resolve_units

# Known SKUs from the real AWS pricing data (also used by tests/contract/test_sku_selections.py
# and tests/unit/test_price_calculation.py's real-data counterparts).
KNOWN_ON_DEMAND_SKU = "NN4EGUUQRWVYP98C"


def test_resolves_unit_for_a_single_sku():
    result = resolve_units([(KNOWN_ON_DEMAND_SKU, "on_demand", "not_applicable")])
    assert result[(KNOWN_ON_DEMAND_SKU, "on_demand", "not_applicable")] == "Hrs"


def test_resolves_units_for_multiple_skus_in_one_call():
    """Batched: multiple distinct SKUs resolved together, not one at a time."""
    other_sku = "QZ9R39S2Y8MCC9Y8"
    result = resolve_units(
        [
            (KNOWN_ON_DEMAND_SKU, "on_demand", "not_applicable"),
            (other_sku, "on_demand", "not_applicable"),
        ]
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
        ]
    )
    assert result[(KNOWN_ON_DEMAND_SKU, "on_demand", "not_applicable")] == "Hrs"
    assert result[("THIS-SKU-DOES-NOT-EXIST", "on_demand", "not_applicable")] is None


def test_empty_input_returns_empty_map():
    assert resolve_units([]) == {}


def test_unit_matches_the_row_lookup_price_actually_prices():
    """A Reserved SKU's price_fact rows include both a recurring-rate row (unit "Hrs") and an
    upfront-quantity row (unit "Quantity") sharing the same term/lease/purchase_option — the
    resolved unit must describe whichever row `lookup_price` actually prices, not an
    arbitrary same-key row, or the displayed unit would mislabel the shown price."""
    sku = "QZ9R39S2Y8MCC9Y8"
    price = lookup_price(sku=sku, pricing_term="reserved_1yr", purchase_option="partial_upfront")
    result = resolve_units([(sku, "reserved_1yr", "partial_upfront")])
    assert price is not None
    assert result[(sku, "reserved_1yr", "partial_upfront")] == "Hrs"
