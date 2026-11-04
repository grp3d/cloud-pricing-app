"""The AWS adapter (019, research R3): wraps the existing AWS code in `catalog.py` and
`pricing.py` without changing it. The one deliberate change is that on-demand prices are read as
all of their tiers (`lookup_price_tiers`), so a tiered SKU is priced by tier (research R8).

An AWS item is its `sku`; SKU codes are already region-scoped.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import Decimal

from src.pricing_data.catalog import (
    find_existing_skus,
    resolve_product_details,
    search_catalog,
)
from src.pricing_data.pricing import (
    lookup_price_tiers,
    lookup_reserved_price,
    resolve_units,
)
from src.pricing_data.providers.base import CatalogItem, ComparablePrice, PriceQuote
from src.pricing_data.snapshot import ActiveSnapshot

_RESERVED_TERMS = {"reserved_1yr", "reserved_3yr"}


def _item(row: dict) -> CatalogItem:
    return CatalogItem(
        provider="aws",
        service_code=row["service_code"],
        service_name=row.get("service_name"),
        product_family=row.get("product_family"),
        sku=row["sku"],
        summary=row.get("summary") or "",
        attributes=row.get("attributes") or {},
        unit=row.get("unit"),
    )


class AwsProvider:
    code = "aws"
    reports_price_types = False

    def locations(self, snapshot: ActiveSnapshot) -> list[str]:
        """Regions present in all five AWS tables (unchanged from `regions.py`)."""
        return sorted(snapshot.common_regions())

    def search(
        self, snapshot: ActiveSnapshot, *, region: str, limit: int, offset: int, **filters: object
    ) -> tuple[list[CatalogItem], int]:
        """`filters`: `service_code`, `product_family`, `text`, `from_region_code`,
        `to_region_code` (the existing AWS search, unchanged). `kind` is not used for AWS."""
        filters.pop("kind", None)
        rows, _used, total = search_catalog(region=region, limit=limit, offset=offset, **filters)
        return [_item(r) for r in rows], total

    def units(
        self, snapshot: ActiveSnapshot, keys: Sequence[tuple[str, str, str]], *, region: str
    ) -> dict[tuple[str, str, str], str | None]:
        return resolve_units(list(keys), region=region, snapshot=snapshot)

    def describe(
        self, snapshot: ActiveSnapshot, items: Sequence[tuple[str, str]], *, region: str
    ) -> dict[tuple[str, str], CatalogItem]:
        details = resolve_product_details(list(items), region=region, snapshot=snapshot)
        return {
            (service_code, sku): CatalogItem(
                provider="aws",
                service_code=service_code,
                service_name=None,
                product_family=d.product_family,
                sku=sku,
                summary="",
                attributes=d.attributes,
                unit=None,
            )
            for (service_code, sku), d in details.items()
            if d.attributes or d.product_family
        }

    def exists(
        self, snapshot: ActiveSnapshot, items: Iterable[tuple[str, str]], *, region: str
    ) -> set[tuple[str, str]]:
        return find_existing_skus(items, region=region, snapshot=snapshot)

    def price(
        self,
        snapshot: ActiveSnapshot,
        *,
        item: str,
        pricing_term: str,
        purchase_option: str,
        region: str,
        options: dict | None = None,
    ) -> PriceQuote | None:
        if pricing_term in _RESERVED_TERMS:
            reserved = lookup_reserved_price(
                sku=item, pricing_term=pricing_term, purchase_option=purchase_option,
                region=region, snapshot=snapshot,
            )
            if reserved is None:
                return None
            return PriceQuote(
                unit="Hrs",
                recurring_rate=_decimal(reserved.recurring_rate),
                upfront_fee=_decimal(reserved.upfront_fee),
            )
        tiers = lookup_price_tiers(
            sku=item, pricing_term=pricing_term, purchase_option=purchase_option,
            region=region, snapshot=snapshot,
        )
        if not tiers:
            return None
        return PriceQuote(unit=None, tiers=tiers)

    def service_key(self, item: CatalogItem) -> str:
        return item.service_code

    def comparable_prices(self, snapshot: ActiveSnapshot) -> list[ComparablePrice]:
        raise NotImplementedError("comparable_prices arrives with Trends (T073)")


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))
