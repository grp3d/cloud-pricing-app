"""GET /providers — the provider selector (spec FR-001–FR-003; 019 contracts §1).

Each provider's status comes from its own snapshot monitor. A provider is `active` exactly when
it has a usable snapshot and the app has a pricing adapter for it, so a button is never enabled
for a provider that can't be searched or priced.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.models.schemas import ProviderOut
from src.pricing_data import active_snapshot
from src.pricing_data.errors import PricingDataUnavailableError
from src.pricing_data.providers.registry import has_adapter
from src.pricing_data.snapshot import PROVIDER_NAMES

router = APIRouter(tags=["providers"])

_NAMES = PROVIDER_NAMES
_USABLE = {"current", "partial", "stale"}
NOT_ENABLED = "not enabled in this version"


def _provider(code: str) -> ProviderOut:
    if not active_snapshot.state_for(code).initialized:
        try:  # the first request after a restart runs the check (as pricing lookups do)
            active_snapshot.get_active_snapshot(code)
        except PricingDataUnavailableError:
            pass
    status, reason = active_snapshot.provider_status(code)
    active = active_snapshot.state_for(code).active
    enabled = status in _USABLE and has_adapter(code)
    if status in _USABLE and not enabled:
        reason = NOT_ENABLED
    return ProviderOut(
        code=code,
        name=_NAMES[code],
        active=enabled,
        status=status,
        reason=reason,
        snapshot_date=active.snapshot_date if active else None,
        snapshot_revision=active.revision if active else None,
    )


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers() -> list[ProviderOut]:
    return [_provider(code) for code in ("aws", "gcp", "azure")]
