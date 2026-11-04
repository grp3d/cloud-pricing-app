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

import uuid
from collections.abc import Sequence
from decimal import Decimal

from src.config import settings
from src.models.orm import Architecture, Collection, SKUSelection
from src.models.schemas import (
    CalculationDuration,
    CalculationResult,
    CalculationWarning,
    PriceComponentOut,
    PriceLineItem,
    SnapshotSelection,
    TierPartOut,
    UnpriceableItem,
)
from src.pricing_data.active_snapshot import get_active_snapshot
from src.pricing_data.providers.base import price_type_label
from src.pricing_data.providers.registry import get_provider
from src.pricing_data.providers.tiers import (
    NOT_PUBLISHED,
    UnpriceableTierError,
    normalize_tiers,
    price_for_duration,
)


class EmptySnapshotError(ValueError):
    """Raised when `POST /catalog/calculate-snapshot` is called with no selections
    (008-ui-updates-corrections, data-model.md) — an empty snapshot has no meaningful prior
    total to adjust."""


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
    # 018-app-cloud-deployment, FR-059: one snapshot (date and revision) for the whole result —
    # 019: the architecture's own provider's (FR-003).
    provider = get_provider(architecture.provider)
    snapshot = get_active_snapshot(provider.code)
    duration_days = _DURATION_DAYS[duration]

    # Gather every SKU Selection: one per Collection SKU, plus one per Connector's attached SKU.
    # Also record each selection's containing component(s) while collections/connectors are
    # still in scope (004, FR-012/FR-013) — a Collection's own name, or a description naming
    # the two Collections a Connector links, since a connector has no name of its own.
    selections = []
    selection_components: dict = {}
    # 010-multi-region-support, data-model.md/research.md §11: each selection's region — its
    # owning Collection's, or, for a Connector-owned selection, that Connector's "from"
    # Collection's. `.get(...)` (not `[...]`) so a selection with no resolvable owner (the
    # `build_transient_architecture` synthetic path, whose Collection is never given a region)
    # falls back to `None` rather than raising — the documented defensive fallback (FR-015).
    selection_regions: dict[uuid.UUID, str | None] = {}
    collection_names = {c.id: c.name for c in architecture.collections if c.deleted_at is None}
    collection_regions = {c.id: c.region for c in architecture.collections if c.deleted_at is None}
    for collection in architecture.collections:
        if collection.deleted_at is not None:
            continue
        selections.extend(collection.sku_selections)
        for selection in collection.sku_selections:
            selection_components[selection.id] = [collection.name]
            selection_regions[selection.id] = getattr(collection, "region", None)
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
            selection_regions[connector.sku_selection.id] = collection_regions.get(
                connector.from_collection_id
            )

    # Batch-resolve billing units for usage-priced selections only (006) — a Reserved
    # selection's cost doesn't depend on unit classification at all (FR-001/FR-002), so there's
    # nothing for this batch to usefully resolve for one; scoping it down keeps the query's
    # purpose honest (003's `resolve_units`, research.md #2). Grouped by region (010-multi-
    # region-support, research.md §11): each call covers only its own region's selections,
    # merged — safe, since AWS SKU codes are themselves region-scoped. 019: through the
    # provider's adapter; Azure and GCP quotes carry their own unit, so this is AWS's lookup.
    on_demand_selections = [
        s for s in selections if _RESERVED_TERM_DAYS.get(s.pricing_term) is None
    ]
    units: dict = {}
    on_demand_by_region: dict[str, list] = {}
    for s in on_demand_selections:
        region = selection_regions.get(s.id)
        if region is None:
            continue
        on_demand_by_region.setdefault(region, []).append(s)
    for region, region_selections in on_demand_by_region.items():
        if provider.reports_price_types:
            continue  # Azure, GCP: the quote's own unit is used
        units.update(
            provider.units(
                snapshot,
                [(s.sku, s.pricing_term, s.purchase_option) for s in region_selections],
                region=region,
            )
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
        region = selection_regions.get(selection.id)
        tier_parts: list[TierPartOut] | None = None
        components: list[PriceComponentOut] | None = None

        if region is None:
            # Defensive fallback only (data-model.md) — expected unreachable given
            # Collection.region/DataConnector.from_collection_id are both NOT NULL; there's no
            # partition to query without one, so this is unpriceable rather than a crash.
            _mark_unpriceable(selection, "no region could be determined for this selection")
            continue

        # 019 (research R3): every price comes from the architecture's provider adapter.
        quote = provider.price(
            snapshot,
            item=selection.sku,
            pricing_term=selection.pricing_term,
            purchase_option=selection.purchase_option,
            region=region,
            options=getattr(selection, "provider_options", None),
        )

        if term_days is not None:
            # Reserved (006): a fully separate procedure from usage pricing below — never
            # reads `usage_quantity` or classifies the unit. An Azure reservation is a whole-term
            # fee with a zero recurring rate (research R6), so it takes the all-upfront path.
            if quote is None or quote.recurring_rate is None:
                _mark_unpriceable(
                    selection,
                    f"{NOT_PUBLISHED}: no recurring rate for term/purchase_option in current "
                    "snapshot",
                )
                continue

            # Recurring rate bills continuously for every hour of the requested duration —
            # never scaled by `usage_quantity` (FR-001).
            displayed_cost = quote.recurring_rate * _HOURS_PER_DAY * Decimal(duration_days)

            if selection.purchase_option != "no_upfront":
                if quote.upfront_fee is None:
                    _mark_unpriceable(
                        selection,
                        "no upfront fee for term/purchase_option in current snapshot despite "
                        f"{selection.purchase_option} requiring one",
                    )
                    continue
                # A duration-proportional share of the one-time upfront fee, in addition to the
                # recurring contribution above — never dropped (FR-002).
                displayed_cost += quote.upfront_fee * Decimal(duration_days) / Decimal(term_days)
            # else: no_upfront has no upfront fee to add (FR-003).
        else:
            # Usage-priced (on demand, savings plan, committed use; 019, research R8): the
            # adapter returns every published tier; the quantity is converted to a 31-day month
            # by its unit class, priced tier by tier, and scaled to the duration
            # (`providers.tiers.price_for_duration`). A single tier gives exactly 004's result
            # (FR-006, SC-003).
            if quote is None or not quote.tiers:
                _mark_unpriceable(
                    selection,
                    f"{NOT_PUBLISHED}: no price for term/purchase_option in current snapshot",
                )
                continue

            unit = quote.unit or units.get(
                (selection.sku, selection.pricing_term, selection.purchase_option)
            )
            try:
                tiered = price_for_duration(
                    normalize_tiers(quote.tiers), selection.usage_quantity, unit, duration_days,
                    quote.unit_class,
                )
            except UnpriceableTierError as exc:
                # A missing tier price, conflicting tiers or an unrecognized unit: excluded,
                # never guessed (FR-005, FR-007).
                _mark_unpriceable(selection, str(exc))
                continue
            displayed_cost = tiered.cost
            if len(tiered.parts) > 1 or len(quote.tiers) > 1:
                tier_parts = [
                    TierPartOut(
                        from_quantity=p.from_quantity, to_quantity=p.to_quantity, rate=p.rate,
                        quantity=p.quantity, cost=p.cost,
                    )
                    for p in tiered.parts
                ]
            if quote.components and len(tiered.parts) == 1:
                # A composite price (GCP machine): each part's share of the one tier's quantity.
                base_quantity = tiered.parts[0].quantity
                components = [
                    PriceComponentOut(
                        label=c.label, sku=c.sku, quantity=c.multiplier * base_quantity,
                        rate=c.rate, cost=c.multiplier * base_quantity * c.rate,
                    )
                    for c in quote.components
                ]

        total += displayed_cost
        line_items.append(
            PriceLineItem(
                sku_selection_id=selection.id,
                service_code=selection.service_code,
                sku=selection.sku,
                price=displayed_cost,
                priceable=True,
                region=region,
                tiers=tier_parts,
                price_type_label=price_type_label(
                    selection.pricing_term, selection.purchase_option
                ),
                components=components,
            )
        )

    warnings = list(_unconnected_vpc_warnings(architecture))

    return CalculationResult(
        snapshot_date=snapshot.snapshot_date,
        snapshot_revision=snapshot.revision,
        duration=duration,
        total_price=total,
        line_items=line_items,
        unpriceable=unpriceable,
        warnings=warnings,
    )


def build_transient_architecture(selections: Sequence[SnapshotSelection]) -> Architecture:
    """Construct a transient (never `session.add()`-ed, never committed) Architecture/
    Collection/SKUSelection object graph from an ad-hoc list of selections
    (008-ui-updates-corrections, US5, research.md §5) — so `calculate_architecture_price()`
    above can price them via the exact same code path every persisted-Architecture
    calculation uses, with no estimate/approximation (Constitution Principle I).

    Every selection is placed in one throwaway Collection — `calculate_architecture_price`
    only cares about the flat set of selections across all of an architecture's Collections,
    never about grouping, so a single Collection is sufficient. Raises `EmptySnapshotError`
    for an empty `selections` list (data-model.md's validation rule) before constructing
    anything.
    """
    if not selections:
        raise EmptySnapshotError("selections must contain at least one entry")

    # 010-multi-region-support: `SnapshotSelection` carries no region (it's a plain prior-
    # pricing-input value, data-model.md — no collection to inherit one from), so this
    # synthetic Collection is pinned to the app's former single global pricing region rather
    # than left unset, preserving this endpoint's exact prior behavior (spec Assumptions: the
    # Price Change mechanism is out of scope for this feature). Out of scope for this feature:
    # a genuinely multi-region-aware snapshot recalculation would need `SnapshotSelection` to
    # carry its own region. 016-canvas-icon-layout, FR-025: that region is the
    # `AWS_PRICING_REGION` setting (default `us-east-1`), no longer a literal here.
    collection = Collection(
        id=uuid.uuid4(),
        type="application_component",
        name="snapshot",
        region=settings.aws_pricing_region,
    )
    collection.sku_selections = [
        SKUSelection(
            id=uuid.uuid4(),
            collection_id=collection.id,
            service_code=s.service_code,
            sku=s.sku,
            pricing_term=s.pricing_term.value,
            purchase_option=s.purchase_option.value,
            usage_quantity=Decimal(s.usage_quantity),
        )
        for s in selections
    ]

    architecture = Architecture(id=uuid.uuid4(), name="snapshot")
    architecture.collections = [collection]
    architecture.connectors = []
    return architecture


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
