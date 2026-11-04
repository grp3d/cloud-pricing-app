"""GET /trends/series (019, contracts §8, FR-011 to FR-015a).

One series per selected provider: the SKUs Changed points of its selected regions (none
selected means all), for one category. A provider without a usable snapshot is
`provider_unavailable`; one whose history is still being built is `building` with the weeks
built so far; one with fewer than two weeks is `not_enough_history`.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import CurrentUser, DbSession
from src.models.schemas import (
    SkusChangedPointOut,
    TrendsCategory,
    TrendSeriesOut,
    TrendSeriesResult,
)
from src.pricing_data import active_snapshot
from src.pricing_data.errors import PricingDataUnavailableError
from src.pricing_data.history.metrics import MAX_WEEKS, skus_changed
from src.pricing_data.history.service import history_store, is_building
from src.pricing_data.snapshot import PROVIDERS
from src.services.categories import Categorizer, load_categorizer

router = APIRouter(tags=["trends"])

_USABLE = {"current", "partial", "stale"}


def _bad(field: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=422, detail=[{"loc": ["query", field], "msg": message, "type": "value_error"}]
    )


def _parse(select: list[str]) -> list[tuple[str, list[str]]]:
    parsed: list[tuple[str, list[str]]] = []
    for item in select:
        provider, _sep, regions = item.partition(":")
        if provider not in PROVIDERS:
            raise _bad("select", f"unknown provider {provider!r}")
        if any(p == provider for p, _ in parsed):
            raise _bad("select", f"{provider} is selected twice")
        parsed.append((provider, sorted({r for r in regions.split(",") if r})))
    return parsed


def _series(provider: str, regions: list[str], category: str, weeks: int,
            categorizer: Categorizer) -> TrendSeriesOut:
    store = history_store(provider)
    state = store.state()
    weeks_total = int(state.get("weeks_total", 0))
    weeks_built = int(state.get("weeks_built", 0))
    if not active_snapshot.state_for(provider).initialized:
        try:  # the first request after a restart runs the check (as `GET /providers` does)
            active_snapshot.get_active_snapshot(provider)
        except PricingDataUnavailableError:
            pass
    status, reason = active_snapshot.provider_status(provider)
    if status not in _USABLE:
        return TrendSeriesOut(provider=provider, regions=regions, status="provider_unavailable",
                              reason=reason, weeks_built=weeks_built, weeks_total=weeks_total,
                              points=[])
    keys = None if category == "all" else (
        lambda present: categorizer.keys_for(provider, category, present)
    )
    points = [SkusChangedPointOut(**asdict(p))
              for p in skus_changed(store, regions=regions, keys=keys, weeks=weeks)]
    # Still being built: a build is running (or has never run), and weeks are missing.
    in_progress = is_building(provider) or state.get("backfill") in (None, "pending", "running")
    if in_progress and (not state or weeks_built < weeks_total):
        result_status = "building"
    elif not points:
        result_status = "not_enough_history"
    else:
        result_status = "ok"
    return TrendSeriesOut(provider=provider, regions=regions, status=result_status,
                          reason=None, weeks_built=weeks_built, weeks_total=weeks_total,
                          points=points)


@router.get("/trends/series", response_model=TrendSeriesResult)
async def trend_series(
    session: DbSession,
    _user: CurrentUser,
    select: Annotated[list[str], Query(min_length=1)],
    category: TrendsCategory = "all",
    weeks: Annotated[int, Query(ge=1, le=MAX_WEEKS)] = MAX_WEEKS,
) -> TrendSeriesResult:
    categorizer = await load_categorizer(session)
    return TrendSeriesResult(
        category=category,
        series=[_series(p, regions, category, weeks, categorizer) for p, regions in _parse(select)],
    )
