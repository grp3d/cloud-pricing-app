"""The active pricing snapshot (016-canvas-icon-layout, US4/US5: FR-014–FR-024, data-model.md
§1–2, research.md §1–5).

Every pricing lookup uses one snapshot date — the *active* one — instead of each call scanning
for the newest folder. The active date only moves to a snapshot the upstream job has finished
writing: one whose `snapshot_date=<D>/` folder exists in all five tables *and* carries a
`_SUCCESS` completion marker in each (FR-015). A pinned date (`ACTIVE_SNAPSHOT_DATE`, FR-018)
overrides that. A background task (`src/main.py`'s lifespan) calls `run_check()` at startup and
then every `SNAPSHOT_CHECK_INTERVAL_SECONDS`; the result, plus the Admin tab's Issues, lives in
memory only and is rebuilt on restart (spec Clarifications, Q4).

`check_snapshots` is the testable core: directory listings in, state changes out — it never
reads Parquet. The icon-coverage analysis (US5) runs from `run_check` when `check_snapshots`
says something changed.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from src.config import settings
from src.pricing_data.errors import PricingDataUnavailableError
from src.pricing_data.snapshot import TABLES

logger = logging.getLogger("cloud_pricing.active_snapshot")

MARKER = "_SUCCESS"
_DATE_PREFIX = "snapshot_date="
_REGION_PREFIX = "region="


class ActiveSnapshotConfigError(RuntimeError):
    """`ACTIVE_SNAPSHOT_DATE` names a snapshot that isn't present in every pricing table — the
    server refuses to start (FR-018, FR-026)."""


@dataclass
class WaitingSnapshot:
    snapshot_date: str
    reason: str


@dataclass
class Issue:
    """A non-blocking problem for the Admin tab's Issues table (FR-022)."""

    kind: str  # "missing_icon" | "missing_regions" | "pinned_incomplete"
    snapshot_date: str
    message: str
    service_code: str | None = None
    service_name: str | None = None
    is_new: bool | None = None
    regions: list[str] | None = None


@dataclass
class ActiveSnapshotState:
    active_date: str | None = None
    pinned: bool = False
    last_check_at: datetime | None = None
    last_check_error: str | None = None
    waiting: list[WaitingSnapshot] = field(default_factory=list)
    marker_mtimes: dict[str, float] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    initialized: bool = False


@dataclass
class CheckResult:
    switched: bool
    previous_date: str | None
    analysis_needed: bool


@dataclass
class _Listing:
    """What one scan found: per table, each snapshot date and whether it carries a marker."""

    dates: dict[str, dict[str, bool]]

    def present_everywhere(self) -> set[str]:
        sets = [set(d) for d in self.dates.values()]
        return set.intersection(*sets) if sets else set()

    def complete(self) -> set[str]:
        return {
            d
            for d in self.present_everywhere()
            if all(self.dates[t][d] for t in TABLES)
        }

    def all_dates(self) -> set[str]:
        return set().union(*(set(d) for d in self.dates.values()))


def _scan(parquet_dir: Path) -> _Listing:
    dates: dict[str, dict[str, bool]] = {}
    for table in TABLES:
        table_dir = parquet_dir / table
        if not table_dir.is_dir():
            raise OSError(f"pricing data table directory not found: {table_dir}")
        dates[table] = {
            entry.name.removeprefix(_DATE_PREFIX): (entry / MARKER).is_file()
            for entry in table_dir.iterdir()
            if entry.is_dir() and entry.name.startswith(_DATE_PREFIX)
        }
    return _Listing(dates)


def _regions(parquet_dir: Path, snapshot_date: str) -> set[str]:
    regions: set[str] = set()
    for table in TABLES:
        date_dir = parquet_dir / table / f"{_DATE_PREFIX}{snapshot_date}"
        if date_dir.is_dir():
            regions |= {
                e.name.removeprefix(_REGION_PREFIX)
                for e in date_dir.iterdir()
                if e.is_dir() and e.name.startswith(_REGION_PREFIX)
            }
    return regions


def _marker_mtimes(parquet_dir: Path, snapshot_date: str) -> dict[str, float]:
    mtimes: dict[str, float] = {}
    for table in TABLES:
        marker = parquet_dir / table / f"{_DATE_PREFIX}{snapshot_date}" / MARKER
        mtimes[table] = marker.stat().st_mtime if marker.is_file() else 0.0
    return mtimes


def _waiting_reason(listing: _Listing, snapshot_date: str) -> str:
    missing = [t for t in TABLES if snapshot_date not in listing.dates[t]]
    if missing:
        return f"missing from {', '.join(missing)}"
    unmarked = [t for t in TABLES if not listing.dates[t][snapshot_date]]
    return f"no completion marker in {', '.join(unmarked)}"


def check_snapshots(
    parquet_dir: Path,
    state: ActiveSnapshotState,
    override: date | None,
    *,
    at_startup: bool,
) -> CheckResult:
    """Decide the active snapshot from what's on disk, updating `state` in place.

    Returns whether the date switched and whether the icon analysis needs to run: at startup,
    on a switch, or when the active date's completion markers were rewritten (FR-023).
    Raises `ActiveSnapshotConfigError` only at startup, for a pinned date that's missing from a
    table (FR-018); any other problem is recorded in `last_check_error` and the active date is
    left as it was.
    """
    previous = state.active_date
    state.last_check_at = datetime.now(UTC)
    state.initialized = True

    try:
        listing = _scan(parquet_dir)
    except OSError as exc:
        state.last_check_error = str(exc)
        logger.error("pricing snapshot check failed: %s", exc)
        return CheckResult(switched=False, previous_date=previous, analysis_needed=False)

    state.last_check_error = None
    state.issues = [i for i in state.issues if i.kind != "pinned_incomplete"]
    complete = listing.complete()

    if override is not None:
        pinned = override.isoformat()
        if pinned not in listing.present_everywhere():
            missing = [t for t in TABLES if pinned not in listing.dates[t]]
            message = (
                f"ACTIVE_SNAPSHOT_DATE={pinned} is not present in every pricing table "
                f"(missing from {', '.join(missing)})"
            )
            if at_startup:
                raise ActiveSnapshotConfigError(message)
            state.last_check_error = message
            return CheckResult(switched=False, previous_date=previous, analysis_needed=False)
        state.pinned = True
        new_active: str | None = pinned
        if pinned not in complete:
            state.issues.insert(
                0,
                Issue(
                    kind="pinned_incomplete",
                    snapshot_date=pinned,
                    message=(
                        f"The pinned snapshot {pinned} has no completion marker in "
                        f"{', '.join(t for t in TABLES if not listing.dates[t][pinned])}; "
                        "it may be only partly written."
                    ),
                ),
            )
    else:
        state.pinned = False
        newest_complete = max(complete) if complete else None
        if newest_complete and (previous is None or newest_complete > previous):
            new_active = newest_complete
        else:
            new_active = previous
        if new_active is None:
            state.last_check_error = (
                "No pricing snapshot is marked complete (_SUCCESS) in every table."
            )

    switched = new_active != previous
    state.active_date = new_active

    if switched and not at_startup and previous is not None and new_active is not None:
        state.issues = [i for i in state.issues if i.kind != "missing_regions"]
        lost = sorted(_regions(parquet_dir, previous) - _regions(parquet_dir, new_active))
        if lost:
            state.issues.append(
                Issue(
                    kind="missing_regions",
                    snapshot_date=new_active,
                    regions=lost,
                    message=(
                        f"Snapshot {new_active} has no data for {', '.join(lost)}, which "
                        f"{previous} had."
                    ),
                )
            )

    newer = [d for d in listing.all_dates() if new_active is None or d > new_active]
    state.waiting = [
        WaitingSnapshot(snapshot_date=d, reason=_waiting_reason(listing, d))
        for d in sorted(newer)
        if d not in complete
    ]

    mtimes = _marker_mtimes(parquet_dir, new_active) if new_active else {}
    markers_changed = bool(state.marker_mtimes) and mtimes != state.marker_mtimes
    state.marker_mtimes = mtimes

    analysis_needed = new_active is not None and (at_startup or switched or markers_changed)
    return CheckResult(switched=switched, previous_date=previous, analysis_needed=analysis_needed)


# --- Process-wide state -------------------------------------------------------------------------

STATE = ActiveSnapshotState()
_lock = threading.Lock()

# The analysis run after a check that changed something: called with the state, the data
# directory, and the previously active date. Defaults to the icon-coverage analysis (US5,
# `icon_coverage.analyze`, imported lazily — it imports this module); tests may swap it.
AnalysisHook = Callable[[ActiveSnapshotState, Path, str | None], None]
_analysis_hook: AnalysisHook | None = None


def set_analysis_hook(hook: AnalysisHook | None) -> None:
    global _analysis_hook
    _analysis_hook = hook


def _default_analysis(state: ActiveSnapshotState, parquet_dir: Path, previous: str | None) -> None:
    from src.pricing_data.icon_coverage import analyze

    analyze(state, parquet_dir, previous)


def run_check(*, at_startup: bool = False) -> CheckResult:
    """One check against the configured data directory, then the icon analysis if needed.
    Serialized, so a slow check never overlaps the next (spec Edge Cases)."""
    with _lock:
        parquet_dir = Path(settings.aws_pricing_parquet_dir)
        result = check_snapshots(
            parquet_dir, STATE, settings.active_snapshot_date, at_startup=at_startup
        )
        if result.analysis_needed:
            try:
                (_analysis_hook or _default_analysis)(STATE, parquet_dir, result.previous_date)
            except Exception:  # noqa: BLE001 — a failed analysis never stops pricing
                logger.exception("icon coverage analysis failed")
        return result


def get_active_snapshot_date() -> str:
    """The snapshot date every pricing lookup must use (FR-014). The first call runs a check if
    the background monitor hasn't yet (scripts, tests); after that it's an in-memory read.
    Raises `PricingDataUnavailableError` (→ HTTP 503) when there's no usable snapshot."""
    if not STATE.initialized:
        run_check(at_startup=True)
    if STATE.active_date is None:
        raise PricingDataUnavailableError(
            STATE.last_check_error or "no active pricing snapshot is available"
        )
    return STATE.active_date
