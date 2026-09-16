"""Unit tests for billing-unit time-period classification
(004-canvas-pricing-improvements, FR-003, FR-004, FR-005)."""

from __future__ import annotations

import pytest

from src.pricing_data.duration import classify_unit


@pytest.mark.parametrize(
    "unit",
    [
        "Hrs",
        "Hours",
        "hours",
        "hour",
        "Hour",
        "Hourly",
        "Instance-hrs",
        "usagehours",
        "vCPU-Hours",
        "seconds",
        "Minute",
        "minutes",
        "minute",
        "callme-minutes",
        "Requests",
        "Request",
        "API Request",
        "GB",
        "second",
        "Second",
        "GB-Seconds",
        "vCPU-Seconds",
        "Lambda-GB-Second",
    ],
)
def test_no_period_units(unit):
    result = classify_unit(unit)
    assert result.category == "no_period"
    assert result.period_days is None


@pytest.mark.parametrize(
    ("unit", "expected_days"),
    [
        ("Months", 31),
        ("Month", 31),
        ("GB-Mo", 31),
        ("GB-month", 31),
        ("vCPU-Months", 31),
        ("IOPS-Mo", 31),
        ("MBPS-Mo", 31),
    ],
)
def test_fixed_period_units(unit, expected_days):
    result = classify_unit(unit)
    assert result.category == "fixed_period"
    assert result.period_days == expected_days


@pytest.mark.parametrize("unit", ["Quantity", "Some Unrecognized Unit", "", None])
def test_unrecognized_units_never_guessed(unit):
    """An unknown, empty, or missing unit is `unrecognized` — never defaulted into either
    bucket (Constitution Principle I)."""
    result = classify_unit(unit)
    assert result.category == "unrecognized"
    assert result.period_days is None
