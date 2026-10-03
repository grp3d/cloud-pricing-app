"""The active pricing snapshot and the monitor that keeps it current (016-canvas-icon-layout
FR-014–FR-024; 018-app-cloud-deployment FR-004–FR-014; data-model.md §2–5, research.md R7).

Every pricing lookup uses one snapshot — the *active* one — taken once per request. Snapshots are
found only through the pipeline's manifests (`PRICING_DATA_URI`): the `latest.json` pointer, or
the pinned date's manifest (`ACTIVE_SNAPSHOT_DATE`). Data folders are never scanned and
`_SUCCESS` markers are never looked for. A local source is read in place; an S3 source goes
through the verified cache (`snapshot_cache`).

A background task (`src/main.py`'s lifespan) calls `run_check()` at startup and then every
`SNAPSHOT_CHECK_INTERVAL_SECONDS`; the Admin tab can ask for one too. The monitor's state lives
in memory only and is rebuilt on restart. `select_snapshot` and `check_snapshots` are the
testable core.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from src.config import settings
from src.logging_config import get_logger
from src.pricing_data.errors import PricingDataUnavailableError
from src.pricing_data.manifest import (
    FailedRegion,
    LatestPointer,
    Manifest,
    RejectedManifest,
    manifest_key,
    parse_manifest,
    parse_pointer,
    validate_manifest,
)
from src.pricing_data.snapshot import TABLES, ActiveSnapshot
from src.pricing_data.storage import LocalStore, S3Store, Store, open_store

logger = get_logger("cloud_pricing.active_snapshot")

PROVIDER = "aws"
NO_SNAPSHOT = "no snapshot available"
OLD_LAYOUT_MESSAGE = (
    "PRICING_DATA_URI points at a directory in the old layout (snapshot_date= folders with "
    "_SUCCESS markers, no aws/manifests/): {root}. That layout is no longer supported. Produce a "
    "supported root by running the pipeline locally, or convert existing data with the "
    "pipeline's history-upload command (upload-history). See docs/configuration.md."
)


class ActiveSnapshotConfigError(RuntimeError):
    """The configured data source can't be used as configured — a bad `ACTIVE_SNAPSHOT_DATE` or
    an old-layout directory. The server refuses to start (FR-004, FR-005)."""


@dataclass
class Issue:
    """A non-blocking problem for the Admin tab's Issues table (FR-014, FR-022)."""

    kind: str  # "missing_icon" | "missing_regions"
    snapshot_date: str
    message: str
    service_code: str | None = None
    service_name: str | None = None
    is_new: bool | None = None
    regions: list[str] | None = None


@dataclass(frozen=True)
class LatestRun:
    """The newest dated manifest, whatever its status (the Admin tab's "latest pipeline run")."""

    snapshot_date: str
    revision: int
    status: str
    failed_regions: list[FailedRegion]


@dataclass
class MonitorState:
    active: ActiveSnapshot | None = None
    last_check_at: datetime | None = None
    last_check_error: str | None = None
    latest_run: LatestRun | None = None
    rejected: RejectedManifest | None = None
    issues: list[Issue] = field(default_factory=list)
    initialized: bool = False
    # Verified S3 cache entries after the last clean-up; None for a local source.
    cache: list | None = None


@dataclass(frozen=True)
class Selection:
    manifest: Manifest | None
    rejected: RejectedManifest | None
    reason: str | None
    pinned: bool


@dataclass(frozen=True)
class CheckResult:
    switched: bool
    previous: ActiveSnapshot | None
    analysis_needed: bool


# --- Selection (pure, plus store reads) ---------------------------------------------------------


def _is_old_layout(store: Store, provider: str) -> bool:
    if not isinstance(store, LocalStore):
        return False
    if (store.root / provider / "manifests").is_dir():
        return False
    return any((store.root / table).is_dir() for table in TABLES)


def _read_manifest(
    store: Store, provider: str, snapshot_date: str
) -> Manifest | RejectedManifest | None:
    raw = store.get(manifest_key(provider, snapshot_date))
    if raw is None:
        return None
    return parse_manifest(raw, snapshot_date=snapshot_date)


def select_snapshot(
    store: Store, provider: str, pinned_date: date | None, *, at_startup: bool
) -> Selection:
    """The manifest to use: the pinned date's, else the one `latest.json` names. Raises
    `ActiveSnapshotConfigError` for an old-layout directory, and at startup for a pin that is
    missing, purged or otherwise unusable (FR-005). Store errors propagate to the caller."""
    if _is_old_layout(store, provider):
        raise ActiveSnapshotConfigError(OLD_LAYOUT_MESSAGE.format(root=store.location))

    if pinned_date is not None:
        pinned = pinned_date.isoformat()
        found = _read_manifest(store, provider, pinned)
        if found is None:
            problem: RejectedManifest = RejectedManifest(pinned, None, "manifest not found")
        elif isinstance(found, RejectedManifest):
            problem = found
        else:
            checked = validate_manifest(found, provider)
            if isinstance(checked, Manifest):
                return Selection(checked, None, None, pinned=True)
            problem = checked
        message = f"ACTIVE_SNAPSHOT_DATE={pinned} can't be used: {problem.reason}"
        if at_startup:
            raise ActiveSnapshotConfigError(message)
        rejected = RejectedManifest(pinned, problem.revision, message)
        return Selection(None, rejected, None, pinned=True)

    raw_pointer = store.get(f"{provider}/manifests/latest.json")
    if raw_pointer is None:
        return Selection(None, None, NO_SNAPSHOT, pinned=False)
    pointer = parse_pointer(raw_pointer)
    if isinstance(pointer, RejectedManifest):
        return Selection(None, pointer, None, pinned=False)
    found = _read_manifest(store, provider, pointer.snapshot_date)
    if found is None:
        return Selection(
            None,
            RejectedManifest(pointer.snapshot_date, pointer.revision,
                             "latest.json names a manifest that does not exist"),
            None,
            pinned=False,
        )
    if isinstance(found, RejectedManifest):
        return Selection(None, found, None, pinned=False)
    checked = validate_manifest(found, provider, pointer=pointer)
    if isinstance(checked, RejectedManifest):
        return Selection(None, checked, None, pinned=False)
    return Selection(checked, None, None, pinned=False)


def previous_snapshot(store: Store, provider: str, snapshot_date: str) -> Manifest | None:
    """The newest usable manifest dated before `snapshot_date` (icon coverage's "new service"
    comparison). Partial, failed and purged dates are skipped."""
    for candidate in reversed(store.list_manifest_dates(provider)):
        if candidate >= snapshot_date:
            continue
        found = _read_manifest(store, provider, candidate)
        if isinstance(found, Manifest) and isinstance(validate_manifest(found, provider), Manifest):
            return found
    return None


def _latest_run(store: Store, provider: str) -> LatestRun | None:
    dates = store.list_manifest_dates(provider)
    if not dates:
        return None
    found = _read_manifest(store, provider, dates[-1])
    if not isinstance(found, Manifest):
        return None
    return LatestRun(found.snapshot_date, found.revision, found.status, found.regions.failed)


# --- One check ----------------------------------------------------------------------------------

Materialize = Callable[..., ActiveSnapshot]


def _is_newer(manifest: Manifest, active: ActiveSnapshot) -> bool:
    return (manifest.snapshot_date, manifest.revision) > (active.snapshot_date, active.revision)


def check_snapshots(
    store: Store,
    provider: str,
    state: MonitorState,
    pinned_date: date | None,
    *,
    at_startup: bool,
    materialize: Materialize,
) -> CheckResult:
    """Decide the active snapshot, updating `state` in place. A newer usable snapshot (or, when
    pinned, the pinned one) is made ready by `materialize` and then swapped in as a whole; any
    problem leaves the active snapshot as it was and is recorded for the Admin tab (FR-013)."""
    previous = state.active
    state.last_check_at = datetime.now(UTC)
    state.initialized = True

    try:
        selection = select_snapshot(store, provider, pinned_date, at_startup=at_startup)
        state.latest_run = _latest_run(store, provider)
    except ActiveSnapshotConfigError:
        if at_startup:
            raise
        state.last_check_error = "the data source is misconfigured; see the server log"
        return CheckResult(False, previous, False)
    except Exception as exc:  # noqa: BLE001 — an unreachable source keeps the current snapshot
        state.last_check_error = f"checking {getattr(store, 'location', store)} failed: {exc}"
        logger.error("pricing snapshot check failed", error=str(exc))
        return CheckResult(False, previous, False)

    state.last_check_error = None
    state.rejected = selection.rejected
    if selection.rejected is not None:
        logger.warning(
            "pricing snapshot rejected",
            snapshot_date=selection.rejected.snapshot_date,
            revision=selection.rejected.revision,
            reason=selection.rejected.reason,
        )

    manifest = selection.manifest
    switch = manifest is not None and (
        previous is None
        or (selection.pinned and (manifest.snapshot_date, manifest.revision)
            != (previous.snapshot_date, previous.revision))
        or (not selection.pinned and _is_newer(manifest, previous))
    )
    if switch:
        try:
            state.active = materialize(manifest, pinned=selection.pinned)
        except Exception as exc:  # noqa: BLE001 — retried at the next check
            state.rejected = RejectedManifest(manifest.snapshot_date, manifest.revision, str(exc))
            logger.warning(
                "pricing snapshot rejected",
                snapshot_date=manifest.snapshot_date,
                revision=manifest.revision,
                reason=str(exc),
            )
            switch = False

    if state.active is None:
        state.last_check_error = (
            selection.reason or (state.rejected.reason if state.rejected else NO_SNAPSHOT)
        )

    if switch and previous is not None and state.active is not None:
        state.issues = [i for i in state.issues if i.kind != "missing_regions"]
        lost = sorted(previous.common_regions() - state.active.common_regions())
        if lost:
            state.issues.append(Issue(
                kind="missing_regions",
                snapshot_date=state.active.snapshot_date,
                regions=lost,
                message=(
                    f"Snapshot {state.active.snapshot_date} has no data for {', '.join(lost)}, "
                    f"which {previous.snapshot_date} had."
                ),
            ))

    analysis_needed = state.active is not None and (at_startup or switch)
    return CheckResult(switch, previous, analysis_needed)


# --- Process-wide state -------------------------------------------------------------------------

STATE = MonitorState()
_lock = threading.Lock()

# The analysis run after a check that changed the active snapshot: called with the state, the
# store and the previously active snapshot. Defaults to the icon-coverage analysis (imported
# lazily — it imports this module); tests may swap it.
AnalysisHook = Callable[[MonitorState, Store, ActiveSnapshot | None], None]
_analysis_hook: AnalysisHook | None = None


def set_analysis_hook(hook: AnalysisHook | None) -> None:
    global _analysis_hook
    _analysis_hook = hook


def reset() -> None:
    """Forget the monitor's state (tests; the next lookup re-checks)."""
    global STATE
    STATE = MonitorState()


def _default_analysis(state: MonitorState, store: Store, previous: ActiveSnapshot | None) -> None:
    from src.pricing_data.icon_coverage import analyze

    analyze(state, store, previous)


def _materializer(store: Store) -> Materialize:
    def materialize(manifest: Manifest, *, pinned: bool) -> ActiveSnapshot:
        if isinstance(store, S3Store):
            from src.pricing_data.snapshot_cache import ensure_cached

            cached = ensure_cached(store, manifest, Path(settings.pricing_cache_dir),
                                   settings.pricing_cache_max_bytes)
            return ActiveSnapshot.from_manifest(cached.manifest, base_dir=cached.path,
                                                pinned=pinned)
        return ActiveSnapshot.from_manifest(manifest, base_dir=store.root, pinned=pinned)

    return materialize


def _log_transitions(result: CheckResult, *, first: bool) -> None:
    """017-structured-json-logging, FR-008 a–b: log what this check changed."""
    active = STATE.active
    if active is None:
        return
    if first and result.switched:
        logger.info(
            "active pricing snapshot selected",
            snapshot_date=active.snapshot_date,
            revision=active.revision,
            pinned=active.pinned,
        )
    elif result.switched:
        logger.info(
            "active pricing snapshot changed",
            snapshot_date=active.snapshot_date,
            revision=active.revision,
            previous_snapshot_date=result.previous.snapshot_date if result.previous else None,
            previous_revision=result.previous.revision if result.previous else None,
            pinned=active.pinned,
        )
        for issue in STATE.issues:
            if issue.kind == "missing_regions" and issue.snapshot_date == active.snapshot_date:
                logger.warning(
                    "pricing snapshot missing regions",
                    snapshot_date=active.snapshot_date,
                    previous_snapshot_date=(
                        result.previous.snapshot_date if result.previous else None
                    ),
                    regions=issue.regions,
                )


def _cleanup_cache(store: S3Store, result: CheckResult) -> None:
    """Delete what the clean-up policy says, then record the cache for the Admin tab."""
    from src.pricing_data.snapshot_cache import apply_cleanup, list_entries, plan_cleanup

    cache_dir = Path(settings.pricing_cache_dir)
    entries = list_entries(cache_dir, PROVIDER)

    def entry_for(snapshot: ActiveSnapshot | None):
        if snapshot is None:
            return None
        return next((e for e in entries if e.path == snapshot.base_dir), None)

    purged: set[str] = set()
    for date_ in {e.snapshot_date for e in entries} - {STATE.active.snapshot_date
                                                        if STATE.active else ""}:
        found = _read_manifest(store, PROVIDER, date_)
        if isinstance(found, Manifest) and found.status == "purged":
            purged.add(date_)
    deletions = plan_cleanup(
        entries,
        active=entry_for(STATE.active),
        keep=settings.pricing_cache_keep,
        max_bytes=settings.pricing_cache_max_bytes,
        superseded_this_check=entry_for(result.previous) if result.switched else None,
        purged_dates=purged,
    )
    if deletions:
        apply_cleanup(deletions)
        logger.info("pricing cache cleaned", deleted=[p.name for p in deletions])
    STATE.cache = list_entries(cache_dir, PROVIDER)


def _post_check(store: Store, result: CheckResult) -> None:
    """Work after a check: the icon analysis on a switch, then cache clean-up (S3 only)."""
    if result.analysis_needed:
        try:
            (_analysis_hook or _default_analysis)(STATE, store, result.previous)
        except Exception:  # noqa: BLE001 — a failed analysis never stops pricing
            logger.exception("icon coverage analysis failed")
    if isinstance(store, S3Store):
        try:
            _cleanup_cache(store, result)
        except Exception:  # noqa: BLE001 — clean-up is retried at the next check
            logger.exception("pricing cache clean-up failed")
    else:
        STATE.cache = None


def run_check(*, at_startup: bool = False) -> CheckResult:
    """One check against the configured source, then the analysis if needed. Serialized, so a
    slow check never overlaps the next (spec Edge Cases)."""
    with _lock:
        store = open_store(settings)
        was_initialized = STATE.initialized
        result = check_snapshots(
            store,
            PROVIDER,
            STATE,
            settings.active_snapshot_date,
            at_startup=at_startup,
            materialize=_materializer(store),
        )
        _log_transitions(result, first=at_startup or not was_initialized)
        _post_check(store, result)
        return result


def check_in_progress() -> bool:
    """Whether a check is running right now (the manual check endpoint answers 409)."""
    if _lock.acquire(blocking=False):
        _lock.release()
        return False
    return True


def get_active_snapshot() -> ActiveSnapshot:
    """The snapshot every pricing lookup must use (FR-014). The first call runs a check if the
    background monitor hasn't yet (scripts, tests); after that it's an in-memory read. Raises
    `PricingDataUnavailableError` (→ HTTP 503) when there's no usable snapshot (FR-013)."""
    if not STATE.initialized:
        run_check(at_startup=True)
    if STATE.active is None:
        raise PricingDataUnavailableError(STATE.last_check_error or NO_SNAPSHOT)
    return STATE.active


def pricing_status() -> tuple[bool, str | None]:
    """(pricing works, a fixed public phrase saying why not) for `/health`. Never includes a
    location or an error text, because `/health` needs no login."""
    state = STATE
    if state.active is not None:
        return True, None
    if not state.initialized:
        return False, "not checked yet"
    if state.last_check_error == NO_SNAPSHOT:
        return False, NO_SNAPSHOT
    if state.rejected is not None:
        return False, "snapshot rejected"
    if state.last_check_error and state.last_check_error.startswith("checking "):
        return False, "data source unreachable"
    return False, "pricing data unavailable"


def get_active_snapshot_date() -> str:
    """The active snapshot's date, for callers outside the pricing-data modules."""
    return get_active_snapshot().snapshot_date


__all__ = [
    "ActiveSnapshotConfigError",
    "CheckResult",
    "Issue",
    "LatestPointer",
    "LatestRun",
    "MonitorState",
    "Selection",
    "check_snapshots",
    "get_active_snapshot",
    "get_active_snapshot_date",
    "previous_snapshot",
    "run_check",
    "select_snapshot",
]
