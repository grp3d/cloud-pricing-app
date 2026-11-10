"""GET /trends/series and GET /trends/movers (019, contracts §8, FR-011 to FR-019).

One series per selected provider: the SKUs Changed points of its selected regions (none
selected means all), for one category. A provider without a usable snapshot is
`provider_unavailable`; one whose history is still being built is `building` with the weeks
built so far; one with fewer than two weeks is `not_enough_history`. Movers use the same
statuses for their one provider.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import CurrentUser, DbSession
from src.models.schemas import (
    MoverOut,
    MoversOut,
    ProviderCode,
    SkusChangedPointOut,
    TrendsCategory,
    TrendSeriesOut,
    TrendSeriesResult,
)
from src.pricing_data import active_snapshot
from src.pricing_data.errors import PricingDataUnavailableError
from src.pricing_data.history.metrics import MAX_WEEKS, Mover, movers, skus_changed
from src.pricing_data.history.service import history_store, is_building
from src.pricing_data.history.store import HistoryStore
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


def _unavailable_reason(provider: str) -> str | None:
    """None when the provider has a usable snapshot, else why not."""
    if not active_snapshot.state_for(provider).initialized:
        try:  # the first request after a restart runs the check (as `GET /providers` does)
            active_snapshot.get_active_snapshot(provider)
        except PricingDataUnavailableError:
            pass
    status, reason = active_snapshot.provider_status(provider)
    return None if status in _USABLE else (reason or "not available")


def _status(provider: str, store: HistoryStore, has_data: bool) -> str:
    state = store.state()
    weeks_total = int(state.get("weeks_total", 0))
    weeks_built = int(state.get("weeks_built", 0))
    # Still being built: a build is running (or has never run), and weeks are missing.
    in_progress = is_building(provider) or state.get("backfill") in (None, "pending", "running")
    if in_progress and (not state or weeks_built < weeks_total):
        return "building"
    return "ok" if has_data else "not_enough_history"


def _keys(provider: str, category: str, categorizer: Categorizer):
    return None if category == "all" else (
        lambda present: categorizer.keys_for(provider, category, present)
    )


def _series(provider: str, regions: list[str], category: str, weeks: int,
            categorizer: Categorizer) -> TrendSeriesOut:
    store = history_store(provider)
    state = store.state()
    weeks_total = int(state.get("weeks_total", 0))
    weeks_built = int(state.get("weeks_built", 0))
    reason = _unavailable_reason(provider)
    if reason is not None:
        return TrendSeriesOut(provider=provider, regions=regions, status="provider_unavailable",
                              reason=reason, weeks_built=weeks_built, weeks_total=weeks_total,
                              points=[])
    points = [SkusChangedPointOut(**asdict(p)) for p in skus_changed(
        store, regions=regions, keys=_keys(provider, category, categorizer), weeks=weeks)]
    return TrendSeriesOut(provider=provider, regions=regions,
                          status=_status(provider, store, bool(points)), reason=None,
                          weeks_built=weeks_built, weeks_total=weeks_total, points=points)


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


NO_CHANGES = "No price changes in this period"
PERIODS = (1, 4, 13, 52)


def _mover_out(m: Mover) -> MoverOut:
    return MoverOut(service_name=m.service_name, description=m.description, region=m.region,
                    unit=m.unit, start_price=str(m.start_price), end_price=str(m.end_price),
                    change_pct=m.change_pct, tier_note=m.tier_note)


@router.get("/trends/movers", response_model=MoversOut)
async def trend_movers(
    session: DbSession,
    _user: CurrentUser,
    provider: ProviderCode,
    category: TrendsCategory = "all",
    regions: str = "",
    period_weeks: int = 52,
) -> MoversOut:
    if period_weeks not in PERIODS:
        raise _bad("period_weeks", f"must be one of {', '.join(map(str, PERIODS))}")
    selected = sorted({r for r in regions.split(",") if r})
    base = {"provider": provider, "category": category, "regions": selected,
            "period_weeks": period_weeks}
    empty = {"from_snapshot": None, "to_snapshot": None, "weeks_available": 0,
             "increases": [], "decreases": []}
    reason = _unavailable_reason(provider)
    if reason is not None:
        return MoversOut(**base, **empty, status="provider_unavailable", reason=reason)
    store = history_store(provider)
    categorizer = await load_categorizer(session)
    result = movers(store, regions=selected, keys=_keys(provider, category, categorizer),
                    period_weeks=period_weeks)
    status = _status(provider, store, result is not None)
    if result is None:
        return MoversOut(**base, **empty, status=status)
    increases = [_mover_out(m) for m in result.increases]
    decreases = [_mover_out(m) for m in result.decreases]
    return MoversOut(
        **base, status=status, from_snapshot=result.from_snapshot,
        to_snapshot=result.to_snapshot, weeks_available=result.weeks_available,
        increases=increases, decreases=decreases,
        message=None if increases or decreases else NO_CHANGES,
    )
