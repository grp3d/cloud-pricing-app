"""Graduated tier pricing, shared by every provider (019, research R8, spec FR-008).

A quantity is split across the tiers and each part is priced at its own tier's rate. With tiers
0–10, 10–20 and 20–1000 and a quantity of 40: 10 × tier 1 + 10 × tier 2 + 20 × tier 3. A
single-tier price is the same calculation with one part, so non-tiered prices are unchanged.

Rules:
- Tiers apply to one line on its own (not pooled across lines or the account).
- A quantity past a bounded top tier is priced at the tier with the highest upper bound.
- Rows with the same start and the same rate collapse to one tier; the same start with different
  rates can't be told apart, so the line is unpriceable.
- A tier with no published rate makes the line unpriceable if the quantity reaches it; it is
  never partly priced (FR-007).

Published tiers are per month. `price_for_duration` converts the line's quantity to the app's
fixed 31-day month by its unit class (`duration.classify_unit`), tiers it, and scales the cost to
the requested duration:

| Unit class | Quantity entered | Monthly quantity | Cost for the duration |
|---|---|---|---|
| no period (hours, GB, requests…) | a steady daily amount | quantity × 31 | month cost × days ÷ 31 |
| fixed period of d days (GB-Mo…) | held over the unit's period | quantity as entered | cost × days ÷ d |
| unrecognized | — | — | unpriceable |

All arithmetic is `Decimal`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from src.pricing_data.duration import UnitClassification, classify_unit
from src.pricing_data.providers.base import Tier, TierPart

MONTH_DAYS = 31
NOT_PUBLISHED = "not published"


class UnpriceableTierError(ValueError):
    """The tiers can't price this quantity; the message is the line's unpriceable reason."""


@dataclass(frozen=True)
class TieredCost:
    parts: list[TierPart]
    cost: Decimal


def normalize_tiers(rows: Iterable[Tier]) -> list[Tier]:
    """Sort by start and collapse duplicate rows. Raises `UnpriceableTierError` for no tiers or
    for two rates at the same start."""
    by_start: dict[Decimal, Tier] = {}
    for tier in rows:
        seen = by_start.get(tier.start_quantity)
        if seen is None:
            by_start[tier.start_quantity] = tier
        elif seen.rate != tier.rate:
            raise UnpriceableTierError(
                f"two different prices are published for the tier starting at "
                f"{tier.start_quantity}"
            )
        elif seen.end_quantity is None and tier.end_quantity is not None:
            by_start[tier.start_quantity] = tier
    if not by_start:
        raise UnpriceableTierError(NOT_PUBLISHED)
    return [by_start[start] for start in sorted(by_start)]


def apply_tiers(tiers: list[Tier], monthly_quantity: Decimal) -> TieredCost:
    """Price `monthly_quantity` over normalized `tiers` (from `normalize_tiers`)."""
    parts: list[TierPart] = []
    remaining = monthly_quantity
    last = len(tiers) - 1
    for index, tier in enumerate(tiers):
        if remaining <= 0:
            break
        upper = tiers[index + 1].start_quantity if index < last else tier.end_quantity
        if index == last:
            # The top tier: anything past a bounded top is priced here too (the tier with the
            # highest upper bound).
            take = remaining
        else:
            take = min(remaining, upper - tier.start_quantity)
        if take <= 0:
            continue
        if tier.rate is None:
            raise UnpriceableTierError(NOT_PUBLISHED)
        parts.append(TierPart(tier.start_quantity, upper, tier.rate, take, take * tier.rate))
        remaining -= take
    return TieredCost(parts, sum((p.cost for p in parts), Decimal(0)))


def price_for_duration(
    tiers: list[Tier],
    quantity: Decimal,
    unit: str | None,
    duration_days: int,
    classification: UnitClassification | None = None,
) -> TieredCost:
    """The tiered cost of `quantity` for `duration_days` (research R8 table). Each part keeps
    its published bounds; its quantity and cost are what it contributes to the duration's total.
    `classification` is the adapter's own unit class (Azure, GCP); without it the AWS table
    classifies `unit`."""
    if classification is None:
        classification = classify_unit(unit)
    days = Decimal(duration_days)
    if classification.category == "no_period":
        month = apply_tiers(tiers, quantity * MONTH_DAYS)
        parts = [
            TierPart(p.from_quantity, p.to_quantity, p.rate,
                     p.quantity * days / MONTH_DAYS, p.cost * days / MONTH_DAYS)
            for p in month.parts
        ]
    elif classification.category == "fixed_period":
        period = Decimal(classification.period_days)
        held = apply_tiers(tiers, quantity)
        parts = [
            TierPart(p.from_quantity, p.to_quantity, p.rate, p.quantity, p.cost * days / period)
            for p in held.parts
        ]
    else:
        raise UnpriceableTierError(
            f"billing unit '{unit}' isn't recognized as time-based; excluded from the "
            f"{duration_days}-day total"
        )
    # The line's cost is the sum of its parts, so the breakdown always adds up exactly. With one
    # part (a non-tiered price) it is exactly today's `price × quantity × days ÷ period`.
    return TieredCost(parts, sum((p.cost for p in parts), Decimal(0)))
