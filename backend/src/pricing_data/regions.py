"""List the regions the active pricing snapshot has data for (010-multi-region-support,
spec FR-017, research.md §3).

018-app-cloud-deployment: read from the active snapshot's manifest — for AWS, the regions present
in all five tables — with no directory listing. 019 (research R5): per provider, through its
adapter; `global` and Azure geographies are never listed.
"""

from __future__ import annotations

from src.pricing_data.active_snapshot import get_active_snapshot
from src.pricing_data.errors import PricingDataUnavailableError
from src.pricing_data.providers.registry import get_provider


def list_available_regions(provider: str = "aws") -> list[str]:
    """The provider's selectable regions in its active snapshot, sorted. Raises
    `PricingDataUnavailableError` when there's no active snapshot or no selectable region —
    the same "never mix partial data" posture the snapshot takes."""
    adapter = get_provider(provider)
    regions = sorted(adapter.locations(get_active_snapshot(adapter.code)))
    if not regions:
        raise PricingDataUnavailableError(
            f"no {adapter.code} region has pricing data", adapter.code
        )
    return regions


def region_display_names(provider: str = "aws") -> dict[str, str]:
    """Display names the provider publishes for its regions (Azure); empty for the others."""
    adapter = get_provider(provider)
    names = getattr(adapter, "display_names", None)
    return names(get_active_snapshot(adapter.code)) if names else {}
