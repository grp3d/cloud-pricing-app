"""GET /catalog/skus — AWS pricing catalog search (spec FR-005)."""

from __future__ import annotations

from fastapi import APIRouter

from src.models.schemas import CatalogSearchResult, CatalogSKUOut
from src.pricing_data.catalog import search_catalog

router = APIRouter(tags=["catalog"])


@router.get("/catalog/skus", response_model=CatalogSearchResult)
async def search_skus(
    region: str,
    service_code: str | None = None,
    product_family: str | None = None,
    q: str | None = None,
    from_region_code: str | None = None,
    to_region_code: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> CatalogSearchResult:
    """010-multi-region-support, spec FR-005: `region` picks which Parquet partition is
    searched — the selected collection's region, or a connector's "from" collection's region
    (FR-006). Distinct from `from_region_code`/`to_region_code`, which remain AWSDataTransfer
    attribute filters unrelated to which partition is read."""
    limit = min(max(limit, 1), 200)
    rows, snapshot_date, total = search_catalog(
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
    next_cursor = str(offset + limit) if len(results) == limit else None
    return CatalogSearchResult(
        results=results, next_cursor=next_cursor, snapshot_date=snapshot_date, total=total
    )
