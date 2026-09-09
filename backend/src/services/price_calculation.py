"""Price calculation service (spec FR-010, FR-011, FR-012, FR-017;
004-canvas-pricing-improvements FR-001-FR-005; 006-fix-reserved-pricing FR-001-FR-006).

Sums every SKU Selection across an Architecture's Collections *and* its Data Connectors'
attached services (FR-010), against the current AWS pricing data, scaled to a selected
`CalculationDuration` (004, FR-001). A SKU with no matching price, or whose billing unit can't be
classified into a recognized time-period category, is flagged and excluded from the total —
never silently dropped, never estimated (FR-011, FR-012; 004 FR-005). Architectures with
unconnected VPC Collections get a non-blocking warning (FR-017).

A Reserved-term selection's cost (006) is computed independently of On-Demand's
unit-classification proration: its recurring rate bills continuously for every hour of the
requested duration (never scaled by `usage_quantity`, which has no Reserved-term meaning —
006, Clarifications), plus, for Partial/All Upfront, a duration-proportional share of the
one-time upfront fee. See `lookup_reserved_price` (pricing_data/pricing.py) for how the two
values are retrieved.
"""

from __future__ import annotations

from decimal import Decimal

from src.models.orm import Architecture
from src.models.schemas import (
    CalculationDuration,
    CalculationResult,
    CalculationWarning,
    PriceLineItem,
    UnpriceableItem,
)
from src.pricing_data.duration import classify_unit
from src.pricing_data.pricing import lookup_price, lookup_reserved_price, resolve_units
from src.pricing_data.snapshot import resolve_latest_snapshot_date

# Day-counts used for every duration-based calculation (004, FR-006) — fixed, never derived from
# a real calendar, so results stay deterministic and reproducible.
_DURATION_DAYS: dict[CalculationDuration, int] = {
    CalculationDuration.one_day: 1,
    CalculationDuration.one_month: 31,
    CalculationDuration.one_year: 365,
}

# A Reserved commitment's own term length, in days — also doubles as the "is this selection
# Reserved?" test (006: branching on `_RESERVED_TERM_DAYS.get(pricing_term) is not None`
# happens *before* any pricing lookup, so the Reserved and On-Demand paths are fully separate
# procedures, research.md #2). This is the proration reference for a Reserved selection's
# upfront-fee share (FR-002) — the recurring-rate contribution doesn't prorate against it at
# all, since it bills continuously for every hour of the requested duration regardless of the
# term's own length (FR-001).
_RESERVED_TERM_DAYS: dict[str, int] = {
    "reserved_1yr": 365,
    "reserved_3yr": 1095,
}

# A Reserved recurring rate bills for every hour of the requested duration, not a "usage per
# day" estimate (FR-001) — this is the hours-per-day multiplier that makes that explicit.
_HOURS_PER_DAY = 24


def calculate_architecture_price(
    architecture: Architecture,
    duration: CalculationDuration = CalculationDuration.one_month,
) -> CalculationResult:
    snapshot_date = resolve_latest_snapshot_date()
    duration_days = _DURATION_DAYS[duration]

    # Gather every SKU Selection: one per Collection SKU, plus one per Connector's attached SKU.
    # Also record each selection's containing component(s) while collections/connectors are
    # still in scope (004, FR-012/FR-013) — a Collection's own name, or a description naming
    # the two Collections a Connector links, since a connector has no name of its own.
    selections = []
    selection_components: dict = {}
    collection_names = {c.id: c.name for c in architecture.collections if c.deleted_at is None}
    for collection in architecture.collections:
        if collection.deleted_at is not None:
            continue
        selections.extend(collection.sku_selections)
        for selection in collection.sku_selections:
            selection_components[selection.id] = [collection.name]
    for connector in architecture.connectors:
        if connector.deleted_at is not None:
            continue
        if connector.sku_selection is not None:
            selections.append(connector.sku_selection)
            from_name = collection_names.get(connector.from_collection_id, "?")
            to_name = collection_names.get(connector.to_collection_id, "?")
            selection_components[connector.sku_selection.id] = [
                f"Data Connector between {from_name} and {to_name}"
            ]

    # Batch-resolve billing units for On-Demand selections only (006) — a Reserved selection's
    # cost no longer depends on unit classification at all (FR-001/FR-002), so there's nothing
    # for this batch to usefully resolve for one; scoping it down keeps the query's purpose
    # honest (003's `resolve_units`, research.md #2).
    on_demand_selections = [
        s for s in selections if _RESERVED_TERM_DAYS.get(s.pricing_term) is None
    ]
    units = resolve_units(
        [(s.sku, s.pricing_term, s.purchase_option) for s in on_demand_selections],
        snapshot_date=snapshot_date,
    )

    line_items: list[PriceLineItem] = []
    unpriceable: list[UnpriceableItem] = []
    total = Decimal("0")

    def _mark_unpriceable(selection, reason: str) -> None:
        unpriceable.append(
            UnpriceableItem(
                sku_selection_id=selection.id,
                service_code=selection.service_code,
                sku=selection.sku,
                reason=reason,
                components=selection_components.get(selection.id, []),
            )
        )
        line_items.append(
            PriceLineItem(
                sku_selection_id=selection.id,
                service_code=selection.service_code,
                sku=selection.sku,
                price=None,
                priceable=False,
            )
        )

    for selection in selections:
        term_days = _RESERVED_TERM_DAYS.get(selection.pricing_term)

        if term_days is not None:
            # Reserved (006): a fully separate procedure from On-Demand below — never reads
            # `usage_quantity`, never calls `lookup_price`/`classify_unit`.
            reserved_price = lookup_reserved_price(
                sku=selection.sku,
                pricing_term=selection.pricing_term,
                purchase_option=selection.purchase_option,
                snapshot_date=snapshot_date,
            )
            if reserved_price is None or reserved_price.recurring_rate is None:
                _mark_unpriceable(
                    selection,
                    "no recurring rate for term/purchase_option in current snapshot",
                )
                continue

            # Recurring rate bills continuously for every hour of the requested duration —
            # never scaled by `usage_quantity` (FR-001).
            displayed_cost = (
                Decimal(str(reserved_price.recurring_rate))
                * _HOURS_PER_DAY
                * Decimal(duration_days)
            )

            if selection.purchase_option != "no_upfront":
                if reserved_price.upfront_fee is None:
                    _mark_unpriceable(
                        selection,
                        "no upfront fee for term/purchase_option in current snapshot despite "
                        f"{selection.purchase_option} requiring one",
                    )
                    continue
                # A duration-proportional share of the one-time upfront fee, in addition to the
                # recurring contribution above — never dropped (FR-002).
                displayed_cost += (
                    Decimal(str(reserved_price.upfront_fee))
                    * Decimal(duration_days)
                    / Decimal(term_days)
                )
            # else: no_upfront has no upfront fee to add (FR-003).
        else:
            # On-demand: unchanged from 004 (FR-006, SC-003) — which proration rule applies
            # depends on the billing unit, classified from the unit `resolve_units` already
            # resolved above.
            unit_price = lookup_price(
                sku=selection.sku,
                pricing_term=selection.pricing_term,
                purchase_option=selection.purchase_option,
                snapshot_date=snapshot_date,
            )
            if unit_price is None:
                _mark_unpriceable(selection, "no price for term/purchase_option in current snapshot")
                continue

            raw_cost = Decimal(str(unit_price)) * selection.usage_quantity
            unit = units.get((selection.sku, selection.pricing_term, selection.purchase_option))
            classification = classify_unit(unit)
            if classification.category == "no_period":
                # Entered quantity is a steady daily rate — scale up to the duration (FR-003).
                displayed_cost = raw_cost * Decimal(duration_days)
            elif classification.category == "fixed_period":
                # raw_cost already covers that unit's own period — rescale to the duration
                # (FR-004).
                displayed_cost = (
                    raw_cost * Decimal(duration_days) / Decimal(classification.period_days)
                )
            else:
                # unrecognized — excluded, never guessed (FR-005).
                _mark_unpriceable(
                    selection,
                    f"billing unit '{unit}' isn't recognized as time-based; excluded "
                    f"from the {duration_days}-day total",
                )
                continue

        total += displayed_cost
        line_items.append(
            PriceLineItem(
                sku_selection_id=selection.id,
                service_code=selection.service_code,
                sku=selection.sku,
                price=displayed_cost,
                priceable=True,
            )
        )

    warnings = list(_unconnected_vpc_warnings(architecture))

    return CalculationResult(
        snapshot_date=snapshot_date,
        duration=duration,
        total_price=total,
        line_items=line_items,
        unpriceable=unpriceable,
        warnings=warnings,
    )


def _unconnected_vpc_warnings(architecture: Architecture):
    """FR-017: warn (never block) when 2+ VPC Collections have no Data Connector between them."""
    vpc_ids = {c.id for c in architecture.collections if c.deleted_at is None and c.type == "vpc"}
    if len(vpc_ids) < 2:
        return

    connected: set = set()
    for connector in architecture.connectors:
        if connector.deleted_at is not None:
            continue
        if connector.from_collection_id in vpc_ids and connector.to_collection_id in vpc_ids:
            connected.add(connector.from_collection_id)
            connected.add(connector.to_collection_id)

    if connected != vpc_ids:
        yield CalculationWarning(
            code="unconnected_vpcs",
            message=(
                f"{len(vpc_ids)} VPC collection(s) exist but are not all connected to each "
                "other by a Data Connector; data flow costs between them may be missing."
            ),
        )
