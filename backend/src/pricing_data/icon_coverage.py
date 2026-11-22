"""Which services in the active pricing snapshot have no canvas icon (016-canvas-icon-layout,
US5: FR-022–FR-024, data-model.md §2–3, research.md §3–4).

Uses `aws_service_icons.json` — generated alongside the canvas's own map by
`scripts/generate_aws_service_icon_map.py` — so the Admin Issues table and the canvas always
agree on which services fall back to the generic AWS icon. A service is reported "new" when its
code isn't in the next-older snapshot date present in every table (markers not required), which
needs nothing persisted between restarts.

018-app-cloud-deployment: services are read from the files the manifests list, and "the
next-older snapshot" is the newest usable manifest before the active one (`previous_snapshot`).

027 (FR-014 to FR-016, research R7): GCP and Azure too, from the maps the 020 generator writes
beside the canvas's (`{gcp,azure}_service_icons.json`) and the services it reads
(`provider_services.read_services`). Only first-party services are listed; Marketplace and
third-party services with no icon are one summary line with their count.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import duckdb

from src.logging_config import get_logger
from src.pricing_data.active_snapshot import (
    PROVIDER,
    Issue,
    MonitorState,
    previous_snapshot,
)
from src.pricing_data.duckdb_conn import connect
from src.pricing_data.provider_services import read_services
from src.pricing_data.snapshot import ActiveSnapshot
from src.pricing_data.snapshot_cache import ENTRY_FILE, entry_name
from src.pricing_data.storage import LocalStore, Store

logger = get_logger("cloud_pricing.icon_coverage")

_HERE = Path(__file__).parent
_FALLBACK = {"aws": "generic AWS icon", "gcp": "generic GCP tile", "azure": "generic Azure tile"}
_NAMES = {"aws": "AWS", "gcp": "GCP", "azure": "Azure"}


@dataclass(frozen=True)
class ServiceRow:
    name: str | None
    first_party: bool = True


@cache
def _mapped_codes(provider: str = PROVIDER) -> frozenset[str]:
    """The service codes the canvas has an icon for (its own generated map)."""
    if provider == PROVIDER:
        document = json.loads((_HERE / "aws_service_icons.json").read_text(encoding="utf-8"))
        return frozenset(document["by_code"]) | frozenset(document["special_codes"])
    document = json.loads((_HERE / f"{provider}_service_icons.json").read_text(encoding="utf-8"))
    return frozenset(document["by_id"])


def _service_rows(snapshot: ActiveSnapshot) -> dict[str, ServiceRow]:
    if snapshot.provider == PROVIDER:
        return {code: ServiceRow(name) for code, name in _services(snapshot).items()}
    try:
        return {s.service_id: ServiceRow(s.name, s.first_party)
                for s in read_services(snapshot.provider, snapshot)}
    except duckdb.IOException:
        return {}


def _services(snapshot: ActiveSnapshot) -> dict[str, str | None]:
    """AWS: service_code -> service_name for one snapshot, from `service_dim` (all regions)."""
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
    """One `missing_icon` issue per first-party service in `snapshot` with no icon, new ones
    first; for GCP and Azure, one `marketplace_without_icons` line for the rest (027)."""
    provider = snapshot.provider
    previous_codes = set(_service_rows(previous)) if previous is not None else None
    return unmatched_issues(provider, snapshot.snapshot_date, _service_rows(snapshot),
                            _mapped_codes(provider), previous_codes)


def unmatched_issues(
    provider: str,
    snapshot_date: str,
    services: dict[str, ServiceRow],
    mapped: frozenset[str],
    previous_codes: set[str] | None,
) -> list[Issue]:
    """The issues for one snapshot's services, given the codes that have an icon. A service is
    new when `previous_codes` (the previous snapshot's) doesn't have it."""
    fallback = _FALLBACK.get(provider, "generic icon")
    issues = [
        Issue(
            kind="missing_icon",
            snapshot_date=snapshot_date,
            service_code=code,
            service_name=row.name,
            is_new=previous_codes is not None and code not in previous_codes,
            # AWS codes are readable; GCP and Azure ones are IDs, so those name the service.
            message=(f"{code if provider == PROVIDER else (row.name or code)} has no icon; "
                     f"it shows the {fallback} on the canvas."),
            provider=provider,
        )
        for code, row in services.items()
        if code not in mapped and row.first_party
    ]
    issues.sort(key=lambda i: (not i.is_new, i.service_code or ""))
    marketplace = sum(1 for code, row in services.items()
                      if code not in mapped and not row.first_party)
    if marketplace:
        name = _NAMES.get(provider, provider)
        issues.append(Issue(
            kind="marketplace_without_icons",
            snapshot_date=snapshot_date,
            count=marketplace,
            message=(f"{marketplace:,} Marketplace and third-party {name} services have no "
                     "icon (not listed)."),
            provider=provider,
        ))
    return issues


def _previous(store: Store, active: ActiveSnapshot) -> ActiveSnapshot | None:
    """The next-older usable snapshot. A local source is read in place; for an S3 source its
    files are local only while still cached, so new-service flags are skipped otherwise."""
    manifest = previous_snapshot(store, active.provider, active.snapshot_date)
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
    state.issues = [i for i in state.issues
                    if i.kind not in ("missing_icon", "marketplace_without_icons")] + unmatched
    # 017-structured-json-logging, FR-008 d: one summary, plus one debug line per service.
    listed = [i for i in unmatched if i.kind == "missing_icon"]
    provider = state.active.provider
    for issue in listed:
        logger.debug(
            "service has no icon",
            provider=provider,
            snapshot_date=state.active.snapshot_date,
            service_code=issue.service_code,
            service_name=issue.service_name,
            is_new=bool(issue.is_new),
        )
    logger.info(
        "icon coverage analyzed",
        provider=provider,
        snapshot_date=state.active.snapshot_date,
        missing_icon_count=len(listed),
        marketplace_without_icons=sum(i.count or 0 for i in unmatched),
        new_service_codes=sorted(i.service_code for i in listed if i.is_new),
    )
