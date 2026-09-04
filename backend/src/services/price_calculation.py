"""Price calculation service (spec FR-010, FR-011, FR-012, FR-017).

Sums every SKU Selection across an Architecture's Collections *and* its Data Connectors'
attached services (FR-010), against the current AWS pricing data. A SKU with no matching price
is flagged as unpriceable and excluded from the total — never silently dropped, never
estimated (FR-011, FR-012). Architectures with unconnected VPC Collections get a non-blocking
warning (FR-017).
"""

from __future__ import annotations

from decimal import Decimal

from src.models.orm import Architecture
from src.models.schemas import (
    CalculationResult,
    CalculationWarning,
    PriceLineItem,
    UnpriceableItem,
)
from src.pricing_data.pricing import lookup_price
from src.pricing_data.snapshot import resolve_latest_snapshot_date


def calculate_architecture_price(architecture: Architecture) -> CalculationResult:
    snapshot_date = resolve_latest_snapshot_date()

    # Gather every SKU Selection: one per Collection SKU, plus one per Connector's attached SKU.
    selections = []
    for collection in architecture.collections:
        if collection.deleted_at is not None:
            continue
        selections.extend(collection.sku_selections)
    for connector in architecture.connectors:
        if connector.deleted_at is not None:
            continue
        if connector.sku_selection is not None:
            selections.append(connector.sku_selection)

    line_items: list[PriceLineItem] = []
    unpriceable: list[UnpriceableItem] = []
    total = Decimal("0")

    for selection in selections:
        unit_price = lookup_price(
            sku=selection.sku,
            pricing_term=selection.pricing_term,
            purchase_option=selection.purchase_option,
            snapshot_date=snapshot_date,
        )
        if unit_price is None:
            unpriceable.append(
                UnpriceableItem(
                    sku_selection_id=selection.id,
                    service_code=selection.service_code,
                    sku=selection.sku,
                    reason="no price for term/purchase_option in current snapshot",
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
            continue

        extended_price = Decimal(str(unit_price)) * selection.usage_quantity
        total += extended_price
        line_items.append(
            PriceLineItem(
                sku_selection_id=selection.id,
                service_code=selection.service_code,
                sku=selection.sku,
                price=extended_price,
                priceable=True,
            )
        )

    warnings = list(_unconnected_vpc_warnings(architecture))

    return CalculationResult(
        snapshot_date=snapshot_date,
        total_price=total,
        line_items=line_items,
        unpriceable=unpriceable,
        warnings=warnings,
    )


def _unconnected_vpc_warnings(architecture: Architecture):
    """FR-017: warn (never block) when 2+ VPC Collections have no Data Connector between them."""
    vpc_ids = {
        c.id for c in architecture.collections if c.deleted_at is None and c.type == "vpc"
    }
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
