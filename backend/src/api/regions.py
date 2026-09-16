"""GET /regions — regions the pricing dataset currently has data for
(010-multi-region-support, spec FR-017)."""

from __future__ import annotations

from fastapi import APIRouter

from src.models.schemas import RegionOut, RegionsOut
from src.pricing_data.regions import list_available_regions

router = APIRouter(tags=["regions"])


@router.get("/regions", response_model=RegionsOut)
async def get_regions() -> RegionsOut:
    return RegionsOut(regions=[RegionOut(code=code) for code in list_available_regions()])
