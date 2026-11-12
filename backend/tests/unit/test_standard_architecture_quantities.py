"""Unit tests for the shared usage-figure formulas (022 research R4, R5).

Every provider's rules convert the AWS reference's workload figures with these functions, so the
expected values below are the ones in the AWS report (`standard_architectures_report.md`).
"""

from __future__ import annotations

from decimal import Decimal

from scripts.standard_architectures import quantities as q


def test_values_match_the_aws_report():
    assert q.always_on(4) == Decimal("96.0000")
    assert q.per_hour_rate(2) == Decimal("48.0000")
    assert q.monthly(10_000_000) == Decimal("322580.6452")
    assert q.daily_dpu(10, 2) == Decimal("20.0000")
    assert q.lambda_gb_seconds(15_000_000, 250, 1024) == Decimal("120967.7419")
    assert q.kinesis_put_payload_units(500_000) == Decimal("660645.1613")
    assert q.as_stored(2000) == Decimal("2000.0000")


def test_execution_seconds_is_executions_times_duration_per_day():
    """15M executions x 250 ms = 3,750,000 s a month -> per day over the 31-day month."""
    assert q.execution_seconds(15_000_000, 250) == Decimal("120967.7419")


def test_monthly_tib_from_mb_is_a_daily_rate_in_tib():
    """500,000 MB a month = 500,000 / 1024^2 TiB a month -> per day."""
    assert q.monthly_tib_from_mb(500_000) == Decimal("0.0154")


def test_aws_rules_module_re_exports_the_same_functions():
    from scripts.standard_architectures import match_rules

    assert match_rules.monthly is q.monthly
    assert match_rules.always_on is q.always_on
