"""Usage for comparisons (024, research R4): which quantities may be carried across providers,
what a stated amount means as an engine quantity, and the default usage per function.

The rule is 022's ("no complex logic to force a mapping"): a quantity is carried over only when
both products bill the same kind of unit, with no scaling at all. GB and GiB are treated as the
same billed unit, as 022's standard architectures do (AWS bills "GB" in binary gigabytes).
Anything else is `Unconvertible` and gets no price (FR-011).

Engine quantities follow the app's convention (`pricing_data/duration.py`): a unit with no
period (hours, GB transferred, requests) is a daily rate the engine scales by the duration's
days; a unit with its own period (GB-month) is the amount held. So "1 instance" is 24 hours a
day, and "1 TB transferred a month" is 1000 / 31 GB a day.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.agent.matching.profiles import FUNCTION_LABELS, ProductProfile

DAYS_PER_MONTH = Decimal(31)


@dataclass(frozen=True)
class Converted:
    quantity: Decimal
    options: dict | None = None
    note: str | None = None


@dataclass(frozen=True)
class Unconvertible:
    reason: str


def convert(source: ProductProfile, quantity: Decimal, target: ProductProfile, *,
            target_provider: str, ram_sku: str | None = None) -> Converted | Unconvertible:
    """The target's engine quantity (and provider options) for the source's usage."""
    if "unknown" in (source.unit_kind, target.unit_kind) or source.unit_kind != target.unit_kind:
        return Unconvertible(
            f"billed per {target.unit_kind.replace('_', ' ')}, not per "
            f"{source.unit_kind.replace('_', ' ')}")
    if target_provider == "gcp" and target.function in ("vm", "managed_db"):
        vcpu, memory = source.specs.get("vcpu"), source.specs.get("memory_gib")
        if vcpu is None or memory is None:
            return Unconvertible("the original's vCPU and memory aren't known, so the machine "
                                 "can't be sized")
        if not ram_sku:
            return Unconvertible("no memory price is published to pair with this machine")
        return Converted(
            Decimal(quantity),
            {"kind": "gcp_machine", "version": 1, "vcpus": int(vcpu),
             "memory_gib": str(Decimal(str(memory)).normalize()), "ram_sku": ram_sku},
            f"sized to {vcpu} vCPU and {Decimal(str(memory)).normalize():f} GiB")
    if target_provider == "azure" and target.function == "vm":
        os = source.specs.get("os", "linux")
        return Converted(Decimal(quantity),
                         {"kind": "azure_vm", "version": 1,
                          "os": "windows" if os == "windows" else "linux"})
    return Converted(Decimal(quantity))


# --- Stated amounts and defaults ----------------------------------------------------------------

# Units a user (or the agent, from what the user said) may state an amount in, per unit kind:
# the factor to the engine quantity. "Per month" amounts of a no-period unit become daily rates.
_STATED: dict[str, dict[str, Decimal]] = {
    "gb_month": {"gb": Decimal(1), "tb": Decimal(1000)},
    "tb_month": {"tb": Decimal(1), "gb": Decimal(1) / Decimal(1000)},
    "gb": {"gb": 1 / DAYS_PER_MONTH, "tb": Decimal(1000) / DAYS_PER_MONTH},
    "tb": {"tb": 1 / DAYS_PER_MONTH, "gb": 1 / (Decimal(1000) * DAYS_PER_MONTH)},
    "hour": {"instances": Decimal(24), "hours": 1 / DAYS_PER_MONTH},
    "request": {"requests": 1 / DAYS_PER_MONTH, "million_requests": Decimal(1_000_000)
                / DAYS_PER_MONTH},
}
STATED_UNITS = sorted({u for units in _STATED.values() for u in units})

_UNIT_WORDS = {"gb": "GB", "tb": "TB", "instances": "instance(s)", "hours": "hours",
               "requests": "requests", "million_requests": "million requests"}


def stated_quantity(unit_kind: str, amount: Decimal, unit: str) -> Converted | Unconvertible:
    """The engine quantity for an amount the user stated ("10 TB", "2 instances")."""
    factors = _STATED.get(unit_kind)
    if factors is None or unit not in factors:
        allowed = ", ".join(sorted(factors)) if factors else "none"
        return Unconvertible(f"an amount in {unit} can't be used for a product billed per "
                             f"{unit_kind.replace('_', ' ')} (use: {allowed})")
    amount = Decimal(amount)
    words = f"{amount.normalize():f} {_UNIT_WORDS[unit]}"
    if unit_kind in ("gb_month", "tb_month"):
        label = f"{words} stored"
    elif unit == "instances":
        label = f"{words} running all day"
    else:
        label = f"{words} a month"
    return Converted(amount * factors[unit], note=label)


@dataclass(frozen=True)
class DefaultUsage:
    amount: Decimal
    unit: str
    label: str


# The app's default usage per function (research R4), used when the user gives no amount.
DEFAULT_USAGE: dict[str, DefaultUsage] = {
    "object_storage": DefaultUsage(Decimal(1), "tb", "1 TB stored for the month"),
    "block_storage": DefaultUsage(Decimal(1), "tb", "1 TB stored for the month"),
    "file_storage": DefaultUsage(Decimal(1), "tb", "1 TB stored for the month"),
    "db_storage": DefaultUsage(Decimal(100), "gb", "100 GB stored for the month"),
    "vm": DefaultUsage(Decimal(1), "instances", "1 instance running all month (730+ hours)"),
    "managed_db": DefaultUsage(Decimal(1), "instances", "1 instance running all month"),
    "cache": DefaultUsage(Decimal(1), "instances", "1 node running all month"),
    "load_balancer": DefaultUsage(Decimal(1), "instances", "1 load balancer all month"),
    "data_transfer": DefaultUsage(Decimal(1), "tb", "1 TB transferred in the month"),
    "object_requests_write": DefaultUsage(Decimal(1), "million_requests", "1 million requests"),
    "object_requests_read": DefaultUsage(Decimal(1), "million_requests", "1 million requests"),
    "dns_queries": DefaultUsage(Decimal(1), "million_requests", "1 million queries"),
    "serverless_requests": DefaultUsage(Decimal(1), "million_requests",
                                        "1 million invocations"),
}


def default_usage(function: str) -> DefaultUsage | None:
    return DEFAULT_USAGE.get(function)


def describe_function(function: str) -> str:
    return FUNCTION_LABELS.get(function, function)
