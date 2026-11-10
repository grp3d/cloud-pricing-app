"""The shared graduated-tier function (019, research R8, FR-008). Constitution V: test-first.

A quantity is split across the tiers and each part is priced at its own tier's rate: with tiers
0–10, 10–20 and 20–1000, a quantity of 40 is 10 at tier 1, 10 at tier 2 and 20 at tier 3.
Published tiers are per month, so a line's quantity is converted to a 31-day month first (the
research R8 table), tiered, and the cost scaled to the requested duration.
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from src.pricing_data.providers.base import Tier, TierPart
from src.pricing_data.providers.tiers import (
    UnpriceableTierError,
    apply_tiers,
    normalize_tiers,
    price_for_duration,
)

R1, R2, R3 = D("0.09"), D("0.085"), D("0.07")
THREE = [Tier(D(0), R1, D(10)), Tier(D(10), R2, D(20)), Tier(D(20), R3, D(1000))]


def test_the_example_splits_40_across_three_tiers():
    result = apply_tiers(normalize_tiers(THREE), D(40))
    assert result.cost == 10 * R1 + 10 * R2 + 20 * R3
    assert result.parts == [
        TierPart(D(0), D(10), R1, D(10), 10 * R1),
        TierPart(D(10), D(20), R2, D(10), 10 * R2),
        TierPart(D(20), D(1000), R3, D(20), 20 * R3),
    ]


def test_a_quantity_inside_the_first_tier_has_one_part():
    result = apply_tiers(normalize_tiers(THREE), D(4))
    assert result.cost == 4 * R1
    assert len(result.parts) == 1


def test_a_single_tier_price_gives_one_part_and_todays_cost():
    result = apply_tiers(normalize_tiers([Tier(D(0), D("0.0416"), None)]), D("730"))
    assert result.cost == D("0.0416") * 730
    assert result.parts == [TierPart(D(0), None, D("0.0416"), D(730), D("0.0416") * 730)]


def test_a_free_first_tier_is_applied_not_skipped():
    tiers = [Tier(D(0), D(0), None), Tier(D(100), D("0.087"), None)]
    result = apply_tiers(normalize_tiers(tiers), D(500))
    assert result.cost == 400 * D("0.087")
    assert result.parts[0] == TierPart(D(0), D(100), D(0), D(100), D(0))


def test_open_tiers_end_where_the_next_one_starts():
    # Azure and GCP publish only tier starts.
    tiers = [Tier(D(0), R1, None), Tier(D(10), R2, None), Tier(D(20), R3, None)]
    assert apply_tiers(normalize_tiers(tiers), D(40)).cost == 10 * R1 + 10 * R2 + 20 * R3


def test_unsorted_rows_are_sorted_by_start():
    result = apply_tiers(normalize_tiers(list(reversed(THREE))), D(40))
    assert [p.rate for p in result.parts] == [R1, R2, R3]


def test_a_quantity_past_a_bounded_top_tier_uses_the_tier_with_the_highest_upper_bound():
    result = apply_tiers(normalize_tiers(THREE), D(1500))
    assert result.cost == 10 * R1 + 10 * R2 + 1480 * R3
    assert result.parts[-1].quantity == D(1480)


def test_a_zero_quantity_costs_nothing():
    result = apply_tiers(normalize_tiers(THREE), D(0))
    assert result.cost == 0


def test_a_null_rate_in_a_reached_tier_is_unpriceable():
    tiers = [Tier(D(0), R1, None), Tier(D(10), None, None)]
    with pytest.raises(UnpriceableTierError, match="not published"):
        apply_tiers(normalize_tiers(tiers), D(40))


def test_a_null_rate_only_in_an_unreached_tier_is_priced():
    tiers = [Tier(D(0), R1, None), Tier(D(10), None, None)]
    assert apply_tiers(normalize_tiers(tiers), D(5)).cost == 5 * R1


def test_duplicate_rows_with_the_same_start_and_rate_collapse():
    tiers = [Tier(D(0), D("0.05"), None), Tier(D(0), D("0.05"), None)]
    normalized = normalize_tiers(tiers)
    assert normalized == [Tier(D(0), D("0.05"), None)]
    assert apply_tiers(normalized, D(3)).cost == D("0.15")


def test_the_same_start_with_different_rates_is_unpriceable():
    with pytest.raises(UnpriceableTierError):
        normalize_tiers([Tier(D(0), D("0.05"), None), Tier(D(0), D("0.06"), None)])


def test_no_tiers_is_unpriceable():
    with pytest.raises(UnpriceableTierError, match="not published"):
        normalize_tiers([])


# --- Monthly normalization (research R8 table) ----------------------------------------------

EGRESS = [Tier(D(0), D("0.09"), D(10240)), Tier(D(10240), D("0.085"), D(51200))]


@pytest.mark.parametrize("days", [1, 31, 365])
def test_a_no_period_unit_tiers_on_quantity_times_31_and_scales_by_days_over_31(days):
    # 660.6 GB a day is 20,478.6 GB a month: 10,240 at 0.09 and 10,238.6 at 0.085.
    quantity = D("660.6")
    monthly = quantity * 31
    month_cost = 10240 * D("0.09") + (monthly - 10240) * D("0.085")
    result = price_for_duration(normalize_tiers(EGRESS), quantity, "GB", days)
    assert abs(result.cost - month_cost * days / 31) < D("1e-20")
    assert sum(p.cost for p in result.parts) == result.cost  # the breakdown adds up exactly


@pytest.mark.parametrize("days", [1, 31, 365])
def test_a_fixed_period_unit_tiers_on_the_quantity_as_entered(days):
    s3 = [Tier(D(0), D("0.023"), D(51200)), Tier(D(51200), D("0.022"), D(512000))]
    quantity = D(60000)  # GB stored
    month_cost = 51200 * D("0.023") + 8800 * D("0.022")
    result = price_for_duration(normalize_tiers(s3), quantity, "GB-Mo", days)
    assert abs(result.cost - month_cost * days / 31) < D("1e-20")
    assert [p.quantity for p in result.parts] == [D(51200), D(8800)]


def test_an_unrecognized_unit_is_unpriceable():
    with pytest.raises(UnpriceableTierError, match="isn't recognized"):
        price_for_duration(normalize_tiers(EGRESS), D(1), "Widgets", 31)


@pytest.mark.parametrize(("unit", "days"), [("Hrs", 1), ("Hrs", 31), ("Hrs", 365),
                                            ("GB-Mo", 1), ("GB-Mo", 365)])
def test_a_single_tier_price_gives_todays_result_in_both_classes(unit, days):
    # Today: no-period → price × quantity × days; fixed-period → price × quantity × days ÷ 31.
    price, quantity = D("0.0416"), D(24)
    expected = price * quantity * days if unit == "Hrs" else price * quantity * days / 31
    result = price_for_duration(normalize_tiers([Tier(D(0), price, None)]), quantity, unit, days)
    assert result.cost == expected
