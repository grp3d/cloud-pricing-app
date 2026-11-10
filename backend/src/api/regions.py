"""GET /regions — regions the pricing dataset currently has data for
(010-multi-region-support, spec FR-017; 019 contracts §2: per provider)."""

from __future__ import annotations

from fastapi import APIRouter

from src.models.schemas import ProviderCode, RegionOut, RegionsOut
from src.pricing_data.regions import list_available_regions, region_display_names

router = APIRouter(tags=["regions"])


@router.get("/regions", response_model=RegionsOut)
async def get_regions(provider: ProviderCode = "aws") -> RegionsOut:
    names = region_display_names(provider)
    return RegionsOut(
        regions=[
            RegionOut(code=code, display_name=names.get(code, code))
            for code in list_available_regions(provider)
        ]
    )
