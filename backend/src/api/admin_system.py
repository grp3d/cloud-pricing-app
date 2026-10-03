"""`/admin/system-info` — the Admin tab's System Information section (016-canvas-icon-layout,
US5: FR-020–FR-022, contracts/api.md §1).

Reads the active pricing snapshot's in-memory state only — never triggers a check or touches
Parquet — so it's always fast. Admin-only, like every other `/admin/*` route.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from src.api.deps import AdminUser
from src.config import settings
from src.models.schemas import IssueOut, SystemInfoOut
from src.pricing_data import active_snapshot
from src.pricing_data.active_snapshot import Issue

router = APIRouter(tags=["admin"])

# Most important first: a pinned half-written snapshot, then lost regions, then icon gaps.
_KIND_ORDER = {"pinned_incomplete": 0, "missing_regions": 1, "missing_icon": 2}


def _issue_order(issue: Issue) -> tuple:
    return (_KIND_ORDER.get(issue.kind, 99), not issue.is_new, issue.service_code or "")


@router.get("/admin/system-info", response_model=SystemInfoOut)
async def get_system_info(_admin: AdminUser) -> SystemInfoOut:
    state = active_snapshot.STATE
    active = state.active
    return SystemInfoOut(
        active_snapshot_date=active.snapshot_date if active else None,
        pinned=bool(active and active.pinned),
        last_check_at=state.last_check_at,
        last_check_error=state.last_check_error,
        check_interval_seconds=settings.snapshot_check_interval_seconds,
        waiting_snapshots=[],
        issues=[IssueOut(**asdict(i)) for i in sorted(state.issues, key=_issue_order)],
    )
