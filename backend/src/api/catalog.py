"""GET /catalog/skus — pricing catalog search (spec FR-005; 019 contracts §3: per provider)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.config import settings
from src.models.schemas import (
    CatalogKind,
    CatalogSearchResult,
    CatalogSKUOut,
    ProviderCode,
)
from src.pricing_data.active_snapshot import get_active_snapshot
from src.pricing_data.catalog import EmptyCatalogFilterError, search_catalog
from src.pricing_data.providers.registry import get_provider

router = APIRouter(tags=["catalog"])


def _field_error(field: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=[{"loc": ["query", field], "msg": message, "type": "value_error"}],
    )


@router.get("/catalog/skus", response_model=CatalogSearchResult)
async def search_skus(
    region: str,
    provider: ProviderCode = "aws",
    service_code: str | None = None,
    product_family: str | None = None,
    q: str | None = None,
    kind: CatalogKind | None = None,
    from_region_code: str | None = None,
    to_region_code: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> CatalogSearchResult:
    """010-multi-region-support, spec FR-005: `region` picks which Parquet partition is
    searched — the selected collection's region, or a connector's "from" collection's region
    (FR-006). Distinct from `from_region_code`/`to_region_code`, which remain AWSDataTransfer
    attribute filters unrelated to which partition is read.

    019: `provider` (default `aws`) picks the adapter. `kind` is an Azure/GCP search preset;
    `from_region_code`/`to_region_code` are AWS-only (422 otherwise)."""
    # 016-canvas-icon-layout, FR-025: page-size default and cap come from settings.
    if limit is None:
        limit = settings.catalog_search_default_limit
    limit = min(max(limit, 1), settings.catalog_search_max_limit)

    if provider == "aws":
        if kind is not None:
            raise _field_error("kind", "kind is a search preset for GCP and Azure only")
        rows, snapshot, total = search_catalog(
            region=region,
            service_code=service_code,
            product_family=product_family,
            text=q,
            from_region_code=from_region_code,
            to_region_code=to_region_code,
            limit=limit,
            offset=offset,
        )
        results = [CatalogSKUOut(**row) for row in rows]
    else:
        for name, value in (("from_region_code", from_region_code),
                            ("to_region_code", to_region_code)):
            if value:
                raise _field_error(name, f"{name} is an AWS data transfer filter")
        if not any([service_code, product_family, q, kind]):
            raise EmptyCatalogFilterError(
                "at least one of service_code, product_family, q or kind is required"
            )
        adapter = get_provider(provider)
        snapshot = get_active_snapshot(adapter.code)
        if region not in adapter.locations(snapshot):
            raise _field_error("region", f"{region} is not a {provider} region with pricing data")
        items, total = adapter.search(
            snapshot, region=region, limit=limit, offset=offset, text=q,
            service_code=service_code, product_family=product_family,
            kind=kind.value if kind else None,
        )
        results = [
            CatalogSKUOut(
                service_code=i.service_code,
                service_name=i.service_name or "",
                product_family=i.product_family or "",
                sku=i.sku,
                summary=i.summary,
                attributes=i.attributes,
                unit=i.unit,
                provider=i.provider,
                location_scope=i.location_scope,
                kind=i.kind,
                price_types=list(i.price_types),
            )
            for i in items
        ]
    next_cursor = str(offset + limit) if len(results) == limit else None
    return CatalogSearchResult(
        results=results,
        next_cursor=next_cursor,
        snapshot_date=snapshot.snapshot_date,
        snapshot_revision=snapshot.revision,
        total=total,
    )
