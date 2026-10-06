"""Which services in the active pricing snapshot have no canvas icon (016-canvas-icon-layout,
US5: FR-022–FR-024, data-model.md §2–3, research.md §3–4).

Uses `aws_service_icons.json` — generated alongside the canvas's own map by
`scripts/generate_aws_service_icon_map.py` — so the Admin Issues table and the canvas always
agree on which services fall back to the generic AWS icon. A service is reported "new" when its
code isn't in the next-older snapshot date present in every table (markers not required), which
needs nothing persisted between restarts.

018-app-cloud-deployment: services are read from the files the manifests list, and "the
next-older snapshot" is the newest usable manifest before the active one (`previous_snapshot`).
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import duckdb

from src.logging_config import get_logger
from src.pricing_data.active_snapshot import PROVIDER, Issue, MonitorState, previous_snapshot
from src.pricing_data.duckdb_conn import connect
from src.pricing_data.snapshot import ActiveSnapshot
from src.pricing_data.snapshot_cache import ENTRY_FILE, entry_name
from src.pricing_data.storage import LocalStore, Store

logger = get_logger("cloud_pricing.icon_coverage")

_ICON_MAP = Path(__file__).with_name("aws_service_icons.json")


@cache
def _mapped_codes() -> frozenset[str]:
    document = json.loads(_ICON_MAP.read_text(encoding="utf-8"))
    return frozenset(document["by_code"]) | frozenset(document["special_codes"])


def _services(snapshot: ActiveSnapshot) -> dict[str, str | None]:
    """service_code -> service_name for one snapshot, from `service_dim` (all regions)."""
    files = [f for region in sorted(snapshot.regions("service_dim"))
             for f in snapshot.files("service_dim", region)]
    if not files:
        return {}
    con = connect()
    try:
        rows = con.execute(
            "SELECT service_code, min(service_name) FROM read_parquet(?) "
            "WHERE service_code IS NOT NULL GROUP BY service_code",
            [files],
        ).fetchall()
    except duckdb.IOException:
        return {}
    finally:
        con.close()
    return dict(rows)


def find_unmatched_services(
    snapshot: ActiveSnapshot, previous: ActiveSnapshot | None
) -> list[Issue]:
    """One `missing_icon` issue per service in `snapshot` with no icon, new ones first."""
    mapped = _mapped_codes()
    current = _services(snapshot)
    previous_codes = set(_services(previous)) if previous is not None else None
    snapshot_date = snapshot.snapshot_date
    issues = [
        Issue(
            kind="missing_icon",
            snapshot_date=snapshot_date,
            service_code=code,
            service_name=name,
            is_new=previous_codes is not None and code not in previous_codes,
            message=f"{code} has no icon; it shows the generic AWS icon on the canvas.",
        )
        for code, name in current.items()
        if code not in mapped
    ]
    return sorted(issues, key=lambda i: (not i.is_new, i.service_code or ""))


def _previous(store: Store, active: ActiveSnapshot) -> ActiveSnapshot | None:
    """The next-older usable snapshot. A local source is read in place; for an S3 source its
    files are local only while still cached, so new-service flags are skipped otherwise."""
    manifest = previous_snapshot(store, PROVIDER, active.snapshot_date)
    if manifest is None:
        return None
    if isinstance(store, LocalStore):
        return ActiveSnapshot.from_manifest(manifest, base_dir=store.root, pinned=False)
    cached = active.base_dir.parent / entry_name(manifest)
    if not (cached / ENTRY_FILE).is_file():
        return None
    return ActiveSnapshot.from_manifest(manifest, base_dir=cached, pinned=False)


def analyze(state: MonitorState, store: Store, _previous_active: ActiveSnapshot | None) -> None:
    """The snapshot monitor's analysis hook (FR-023): replace the missing-icon issues for the
    active snapshot, keeping the monitor's own region issues."""
    if state.active is None:
        return
    unmatched = find_unmatched_services(state.active, _previous(store, state.active))
    state.issues = [i for i in state.issues if i.kind != "missing_icon"] + unmatched
    # 017-structured-json-logging, FR-008 d: one summary, plus one debug line per service.
    for issue in unmatched:
        logger.debug(
            "service has no icon",
            snapshot_date=state.active.snapshot_date,
            service_code=issue.service_code,
            service_name=issue.service_name,
            is_new=bool(issue.is_new),
        )
    logger.info(
        "icon coverage analyzed",
        snapshot_date=state.active.snapshot_date,
        missing_icon_count=len(unmatched),
        new_service_codes=sorted(i.service_code for i in unmatched if i.is_new),
    )
