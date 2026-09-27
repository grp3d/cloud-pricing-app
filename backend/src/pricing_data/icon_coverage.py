"""Which services in the active pricing snapshot have no canvas icon (016-canvas-icon-layout,
US5: FR-022–FR-024, data-model.md §2–3, research.md §3–4).

Uses `aws_service_icons.json` — generated alongside the canvas's own map by
`scripts/generate_aws_service_icon_map.py` — so the Admin Issues table and the canvas always
agree on which services fall back to the generic AWS icon. A service is reported "new" when its
code isn't in the next-older snapshot date present in every table (markers not required), which
needs nothing persisted between restarts.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import duckdb

from src.pricing_data.active_snapshot import ActiveSnapshotState, Issue
from src.pricing_data.snapshot import TABLES

_ICON_MAP = Path(__file__).with_name("aws_service_icons.json")


@cache
def _mapped_codes() -> frozenset[str]:
    document = json.loads(_ICON_MAP.read_text(encoding="utf-8"))
    return frozenset(document["by_code"]) | frozenset(document["special_codes"])


def _services(parquet_dir: Path, snapshot_date: str) -> dict[str, str | None]:
    """service_code -> service_name for one snapshot, from `service_dim` (all regions)."""
    pattern = parquet_dir / "service_dim" / f"snapshot_date={snapshot_date}" / "**" / "*.parquet"
    con = duckdb.connect(":memory:")
    try:
        rows = con.execute(
            "SELECT service_code, min(service_name) FROM read_parquet(?) "
            "WHERE service_code IS NOT NULL GROUP BY service_code",
            [str(pattern)],
        ).fetchall()
    except duckdb.IOException:
        return {}
    finally:
        con.close()
    return dict(rows)


def previous_present_date(parquet_dir: Path, snapshot_date: str) -> str | None:
    """The newest date older than `snapshot_date` whose folder exists in all five tables."""
    per_table = [
        {
            e.name.removeprefix("snapshot_date=")
            for e in (parquet_dir / table).iterdir()
            if e.is_dir() and e.name.startswith("snapshot_date=")
        }
        for table in TABLES
        if (parquet_dir / table).is_dir()
    ]
    if len(per_table) != len(TABLES):
        return None
    older = {d for d in set.intersection(*per_table) if d < snapshot_date}
    return max(older) if older else None


def find_unmatched_services(
    parquet_dir: Path, snapshot_date: str, previous_date: str | None
) -> list[Issue]:
    """One `missing_icon` issue per service in `snapshot_date` with no icon, new ones first."""
    mapped = _mapped_codes()
    current = _services(parquet_dir, snapshot_date)
    previous = set(_services(parquet_dir, previous_date)) if previous_date else None
    issues = [
        Issue(
            kind="missing_icon",
            snapshot_date=snapshot_date,
            service_code=code,
            service_name=name,
            is_new=previous is not None and code not in previous,
            message=f"{code} has no icon; it shows the generic AWS icon on the canvas.",
        )
        for code, name in current.items()
        if code not in mapped
    ]
    return sorted(issues, key=lambda i: (not i.is_new, i.service_code or ""))


def analyze(state: ActiveSnapshotState, parquet_dir: Path, _previous_active: str | None) -> None:
    """The active-snapshot monitor's analysis hook (FR-023): replace the missing-icon issues for
    the active date, keeping the monitor's own region and pinned-snapshot issues."""
    if state.active_date is None:
        return
    unmatched = find_unmatched_services(
        parquet_dir, state.active_date, previous_present_date(parquet_dir, state.active_date)
    )
    state.issues = [i for i in state.issues if i.kind != "missing_icon"] + unmatched
