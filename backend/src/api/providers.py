"""GET /providers — the landing page's provider selector (spec FR-003)."""

from __future__ import annotations

from fastapi import APIRouter

from src.models.schemas import ProviderOut

router = APIRouter(tags=["providers"])

_PROVIDERS = [
    ProviderOut(code="aws", name="AWS", active=True),
    ProviderOut(code="gcp", name="GCP", active=False),
    ProviderOut(code="azure", name="Azure", active=False),
]


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers() -> list[ProviderOut]:
    return _PROVIDERS
