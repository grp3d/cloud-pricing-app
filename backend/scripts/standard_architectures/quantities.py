"""Usage-figure formulas shared by every provider's standard-architecture match rules
(014 research.md §5; 022 research R4, R5).

Quantities follow the pricing engine's daily-rate convention: `no_period` units (hours,
requests, GB transferred, ...) take a per-day rate; `fixed_period` units (GB-months, MAU, ...)
take the stored or monthly amount as-is. All three providers convert the AWS reference's
workload figures with these same functions, so the three versions of a design stay comparable.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_Q = Decimal("0.0001")
_DAYS_PER_MONTH = Decimal(31)  # the pricing engine's fixed month (004, FR-006)
_HOURS_PER_DAY = Decimal(24)
_KINESIS_PAYLOAD_UNIT_KB = Decimal(25)


def _q(value: Decimal) -> Decimal:
    """Round to `SKUSelection.usage_quantity`'s `Numeric(18, 4)`."""
    return value.quantize(_Q, rounding=ROUND_HALF_UP)


# --- Quantity formulas (research.md §5) ----------------------------------------------------


def always_on(count: int | Decimal) -> Decimal:
    """An always-on resource (730 running hours/month in the source) — 24 hours/day each."""
    return _q(Decimal(count) * _HOURS_PER_DAY)


def per_hour_rate(units_per_hour: int | Decimal) -> Decimal:
    """A continuous per-hour rate (e.g. load balancer LCUs) — 24 hours/day."""
    return _q(Decimal(units_per_hour) * _HOURS_PER_DAY)


def monthly(amount_per_month: int | Decimal) -> Decimal:
    """A monthly count (requests, queries, GB transferred, TB scanned) as a daily rate."""
    return _q(Decimal(amount_per_month) / _DAYS_PER_MONTH)


def daily_dpu(dpus: int | Decimal, hours_per_day: int | Decimal) -> Decimal:
    return _q(Decimal(dpus) * Decimal(hours_per_day))


def lambda_gb_seconds(executions_per_month: int, avg_duration_ms: int, memory_mb: int) -> Decimal:
    """Lambda compute: executions x duration (s) x memory (GB), as a daily rate."""
    gb_seconds = (
        Decimal(executions_per_month)
        * (Decimal(avg_duration_ms) / Decimal(1000))
        * (Decimal(memory_mb) / Decimal(1024))
    )
    return _q(gb_seconds / _DAYS_PER_MONTH)


def fargate_vcpu(pods: int, vcpu_per_pod: int | Decimal) -> Decimal:
    return _q(Decimal(pods) * Decimal(vcpu_per_pod) * _HOURS_PER_DAY)


def fargate_gb(pods: int, gb_per_pod: int | Decimal) -> Decimal:
    return _q(Decimal(pods) * Decimal(gb_per_pod) * _HOURS_PER_DAY)


def kinesis_put_payload_units(mb_per_month: int | Decimal) -> Decimal:
    """Kinesis PUT payload units (25 KB chunks) from ingested MB/month, as a daily rate."""
    units = Decimal(mb_per_month) * Decimal(1024) / _KINESIS_PAYLOAD_UNIT_KB
    return _q(units / _DAYS_PER_MONTH)


def as_stored(amount: int | Decimal) -> Decimal:
    """A stored amount or monthly per-unit count billed per month — entered unconverted."""
    return _q(Decimal(amount))


def execution_seconds(executions_per_month: int, avg_duration_ms: int) -> Decimal:
    """Execution time (s) of a function at one instance per execution, as a daily rate (022:
    Cloud Run functions vCPU-seconds at the default 1 vCPU)."""
    seconds = Decimal(executions_per_month) * (Decimal(avg_duration_ms) / Decimal(1000))
    return _q(seconds / _DAYS_PER_MONTH)


def monthly_tib_from_mb(mb_per_month: int | Decimal) -> Decimal:
    """A monthly data volume in MB, as a daily rate in TiB (022: Pub/Sub throughput)."""
    return _q(Decimal(mb_per_month) / Decimal(1024) / Decimal(1024) / _DAYS_PER_MONTH)
