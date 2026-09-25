"""Billing-unit -> time-period classification (004, FR-003, FR-004, FR-005, research.md #2).

Built from the real AWS billing-unit label variants confirmed present in the pricing data during
clarification — a small, explicit, auditable table rather than a heuristic parser, so an
unrecognized variant is safely excluded (FR-005) rather than guessed. Classification runs on the
`unit` string `resolve_units` (003) already resolves for a selection — no additional DuckDB
query.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

UnitCategory = Literal["no_period", "fixed_period", "unrecognized"]


@dataclass(frozen=True)
class UnitClassification:
    category: UnitCategory
    # Set only when category == "fixed_period" — the number of days that unit's own period
    # represents (FR-006's 31-day month convention).
    period_days: int | None = None


# No inherent time period — the entered usage quantity is treated as a steady daily rate and
# scaled by the selected duration's day-count directly (FR-003).
_NO_PERIOD_UNITS: frozenset[str] = frozenset(
    {
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
        "1K tokens",
        "1M tokens",
        "Transformations",
        "Messages",
        "Images Processed",
        "Tasks",
        "Pages",
        "Count",
        "Unit",
        "Units",
        "sms-message",
        "Position",
        "image",
        "second",
        "Second",
        "GB-Seconds",
        "vCPU-Seconds",
        "Lambda-GB-Second",
        # 014-architecture-templates-import-export (research.md §6): units the standard
        # architectures' SKUs bill in — each is a usage count or a per-hour/per-request rate by
        # AWS's own definition, so the entered quantity is a steady daily rate like the above.
        "LCU-Hrs",
        "Queries",
        "ShardHour",
        "PutRequest",
        "DPU-Hour",
        "Terabytes",
        "RPU-Hr",
        "ReadRequestUnits",
        "WriteRequestUnits",
        "GB-Hours",
        "Notifications",
    }
)

# Already denominated per a fixed period — cost is scaled between that period and the selected
# duration rather than treated as a daily rate (FR-004). period_days matches FR-006's 31-day
# month convention for every month-family unit found in the real data.
_FIXED_PERIOD_UNITS: dict[str, int] = {
    "Months": 31,
    "Month": 31,
    "GB-Mo": 31,
    "GB-month": 31,
    "vCPU-Months": 31,
    "IOPS-Mo": 31,
    "MBPS-Mo": 31,
    # 014 (research.md §6): per-month units — stored objects, monthly fees, monthly active users.
    "Obj-Month": 31,
    "Mo": 31,
    "CognitoUserPoolsMAU": 31,
    "GigaBytesMonth": 31,
}


def classify_unit(unit: str | None) -> UnitClassification:
    """Classify a billing-unit string per FR-003/FR-004/FR-005. `None`, empty, or anything
    outside the two recognized tables above is `unrecognized` — never guessed (Constitution
    Principle I)."""
    if unit in _NO_PERIOD_UNITS:
        return UnitClassification(category="no_period")
    if unit in _FIXED_PERIOD_UNITS:
        return UnitClassification(category="fixed_period", period_days=_FIXED_PERIOD_UNITS[unit])
    return UnitClassification(category="unrecognized")
