"""GET /catalog/skus — AWS pricing catalog search (spec FR-005)."""

from __future__ import annotations

from fastapi import APIRouter

from src.models.schemas import CatalogSearchResult, CatalogSKUOut
from src.pricing_data.catalog import search_catalog

router = APIRouter(tags=["catalog"])


@router.get("/catalog/skus", response_model=CatalogSearchResult)
async def search_skus(
    service_code: str | None = None,
    product_family: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> CatalogSearchResult:
    limit = min(max(limit, 1), 200)
    rows, snapshot_date = search_catalog(
        service_code=service_code,
        product_family=product_family,
        text=q,
        limit=limit,
        offset=offset,
    )
    results = [CatalogSKUOut(**row) for row in rows]
    next_cursor = str(offset + limit) if len(results) == limit else None
    return CatalogSearchResult(
        results=results, next_cursor=next_cursor, snapshot_date=snapshot_date
    )
