"""Azure and GCP unit tables (019, T031, research R7)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.pricing_data.providers.units import parse_azure_unit, parse_gcp_unit


@pytest.mark.parametrize(
    ("form", "multiplier", "base", "category", "period"),
    [
        ("1 Hour", 1, "Hour", "no_period", None),
        ("100 Hours", 100, "Hours", "no_period", None),
        ("1 GB/Month", 1, "GB/Month", "fixed_period", 31),
        ("10K", 10_000, "", "no_period", None),
        ("1M", 1_000_000, "", "no_period", None),
        ("1/Month", 1, "/Month", "fixed_period", 31),
        ("1 GB", 1, "GB", "no_period", None),
        ("1/Day", 1, "/Day", "fixed_period", 1),
    ],
)
def test_azure_forms(form, multiplier, base, category, period):
    parsed = parse_azure_unit(form)
    assert parsed.multiplier == Decimal(multiplier)
    assert parsed.base == base
    assert parsed.classification.category == category
    assert parsed.classification.period_days == period


@pytest.mark.parametrize("form", ["1 Widget", "per hour", "", None, "0 Hour", "1 GB/Fortnight"])
def test_azure_unknown_forms_are_unrecognized(form):
    assert parse_azure_unit(form).classification.category == "unrecognized"


@pytest.mark.parametrize(
    ("unit", "category", "period"),
    [
        ("h", "no_period", None),
        ("GiBy.h", "no_period", None),
        ("GiBy", "no_period", None),
        ("count", "no_period", None),
        ("GiBy.mo", "fixed_period", 31),
        ("mo", "fixed_period", 31),
        ("GiBy.d", "fixed_period", 1),
    ],
)
def test_gcp_units(unit, category, period):
    parsed = parse_gcp_unit(unit, Decimal("1.000000000"))
    assert parsed.multiplier == 1
    assert parsed.classification.category == category
    assert parsed.classification.period_days == period


def test_gcp_unit_quantity_is_the_price_block():
    # A price for 1,000 requests: the rate per request is price ÷ 1000.
    parsed = parse_gcp_unit("count", Decimal("1000.000000000"))
    assert parsed.multiplier == Decimal(1000)
    assert Decimal("0.4") / parsed.multiplier == Decimal("0.0004")


@pytest.mark.parametrize(("unit", "qty"), [("furlong", 1), ("h", 0), ("h", None), (None, 1)])
def test_gcp_unknown_or_bad_units_are_unrecognized(unit, qty):
    assert parse_gcp_unit(unit, qty).classification.category == "unrecognized"
