"""`/admin/system-info` and `/admin/pricing-snapshot/check` — the Admin tab's System Information
section (016-canvas-icon-layout, US5: FR-020–FR-022; 018-app-cloud-deployment, FR-012, FR-014,
contracts/admin-api.md).

`system-info` reads the snapshot monitor's in-memory state only — never triggers a check or
touches Parquet — so it's always fast. The check endpoint starts one serialized check in the
background. Admin-only, like every other `/admin/*` route.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from src.api.deps import AdminUser
from src.config import settings
from src.logging_config import get_logger
from src.models.schemas import (
    ActiveSnapshotOut,
    CacheEntryOut,
    CacheOut,
    DeploymentOut,
    FailedRegionOut,
    IssueOut,
    LatestRunOut,
    RejectedOut,
    SnapshotCheckStartedOut,
    SourceOut,
    SystemInfoOut,
)
from src.pricing_data import active_snapshot
from src.pricing_data.active_snapshot import Issue

router = APIRouter(tags=["admin"])
logger = get_logger("cloud_pricing.admin_system")

# Most important first: lost regions, then icon gaps.
_KIND_ORDER = {"missing_regions": 0, "missing_icon": 1}
_background: set[asyncio.Task] = set()
# A manual check that has been accepted but may not have taken the monitor lock yet. Checked and
# set with no await in between, so on the event loop two requests can't both see it clear.
_manual_check_pending = False


def _issue_order(issue: Issue) -> tuple:
    return (_KIND_ORDER.get(issue.kind, 99), not issue.is_new, issue.service_code or "")


def _failed(regions) -> list[FailedRegionOut]:
    return [FailedRegionOut(region=f.region, reason=f.reason, attempts=f.attempts) for f in regions]


def _source() -> SourceOut:
    source = settings.pricing_data_source
    location = source.root if source.kind == "local" else f"s3://{source.root}"
    return SourceOut(kind=source.kind, location=location, provider=active_snapshot.PROVIDER)


@router.get("/admin/system-info", response_model=SystemInfoOut)
async def get_system_info(_admin: AdminUser) -> SystemInfoOut:
    state = active_snapshot.STATE
    active = state.active
    active_out = None
    if active is not None:
        manifest = active.manifest
        active_out = ActiveSnapshotOut(
            snapshot_date=active.snapshot_date,
            revision=active.revision,
            run_id=manifest.run_id,
            pipeline_version=manifest.run.pipeline_version.image_tag,
            created_at=manifest.created_at,
            pinned=active.pinned,
            regions=sorted(active.common_regions()),
            failed_regions=_failed(manifest.regions.failed),
        )
    latest = state.latest_run
    cache_out = None
    if state.cache is not None:
        cache_out = CacheOut(
            total_bytes=sum(e.bytes for e in state.cache),
            max_bytes=settings.pricing_cache_max_bytes,
            entries=[
                CacheEntryOut(
                    snapshot_date=e.snapshot_date,
                    revision=e.revision,
                    state=(
                        "active" if active is not None and e.path == active.base_dir else "cached"
                    ),
                    bytes=e.bytes,
                )
                for e in state.cache
            ],
        )
    return SystemInfoOut(
        deployment=DeploymentOut(
            environment=settings.app_environment, release=settings.app_release
        ),
        source=_source(),
        active=active_out,
        latest_run=(
            LatestRunOut(snapshot_date=latest.snapshot_date, revision=latest.revision,
                         status=latest.status, failed_regions=_failed(latest.failed_regions))
            if latest is not None else None
        ),
        rejected=(
            RejectedOut(**asdict(state.rejected)) if state.rejected is not None else None
        ),
        cache=cache_out,
        last_check_at=state.last_check_at,
        last_check_error=state.last_check_error,
        check_interval_seconds=settings.snapshot_check_interval_seconds,
        issues=[IssueOut(**asdict(i)) for i in sorted(state.issues, key=_issue_order)],
    )


@router.post(
    "/admin/pricing-snapshot/check",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SnapshotCheckStartedOut,
    responses={409: {"description": "A check is already running"}},
)
async def start_snapshot_check(_admin: AdminUser) -> SnapshotCheckStartedOut | JSONResponse:
    """Run one check now (FR-012), serialized with the background check. The result appears in
    `system-info` once it finishes."""
    global _manual_check_pending
    if _manual_check_pending or active_snapshot.check_in_progress():
        return JSONResponse(status_code=409, content={"error": "check_in_progress"})
    _manual_check_pending = True

    async def check() -> None:
        global _manual_check_pending
        try:
            await asyncio.to_thread(active_snapshot.run_check)
        except Exception:  # noqa: BLE001 — recorded in the monitor state and the log
            logger.exception("manual pricing snapshot check failed")
        finally:
            _manual_check_pending = False

    task = asyncio.create_task(check())
    _background.add(task)
    task.add_done_callback(_background.discard)
    logger.info("manual pricing snapshot check started")
    return SnapshotCheckStartedOut(started=True)
