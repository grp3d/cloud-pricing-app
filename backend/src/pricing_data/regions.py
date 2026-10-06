"""List the AWS regions the active pricing snapshot has data for (010-multi-region-support,
spec FR-017, research.md §3).

018-app-cloud-deployment: read from the active snapshot's manifest — the regions present in all
five tables — with no directory listing and no DuckDB query. Cheap enough to call wherever a
region needs validating, with no caching layer (Constitution Principle VI).
"""

from __future__ import annotations

from src.pricing_data.active_snapshot import get_active_snapshot
from src.pricing_data.errors import PricingDataUnavailableError


def list_available_regions() -> list[str]:
    """Every region present in all 5 pricing tables of the active snapshot, sorted. Raises
    `PricingDataUnavailableError` when there's no active snapshot or no region is common to all
    five tables — the same "never mix partial data" posture the snapshot takes."""
    common = get_active_snapshot().common_regions()
    if not common:
        raise PricingDataUnavailableError("no region is common to all pricing tables")
    return sorted(common)
