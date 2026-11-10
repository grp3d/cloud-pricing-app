"""The price history builder (019, research R10, data-model §7).

Snapshots are grouped by ISO week; the latest non-purged snapshot (latest revision) of each week
represents it. Each pair of consecutive weeks gets `changes` (items whose price changed) and
`counts` (per location and service key: compared, unchanged, increased, decreased, added,
removed, excluded). A missing week is a gap: the pair spans it.

Only a valid, non-zero price at both ends is compared; a missing or zero price at either end is
excluded; an item at only one end is added or removed, never a change.

The build is incremental and resumable:

- A pair is up to date when its `pair.json` names the same two snapshots (date and revision) and
  the same builder version, and its files read back. Only stale pairs are built.
- A snapshot's price list is computed only when a pair next to it is stale, so a snapshot already
  processed is never fetched again; a new revision of a week rebuilds the pairs on both sides.
- Snapshots are processed oldest to newest, one at a time, and only the newest price list is kept.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from src.logging_config import get_logger
from src.pricing_data.duckdb_conn import connect, spilling
from src.pricing_data.history.store import PAIR_FILE, HistoryStore, write_json
from src.pricing_data.manifest import Manifest
from src.pricing_data.providers._sql import _list
from src.pricing_data.snapshot import ActiveSnapshot

# Bump when the files' meaning changes: every pair is rebuilt.
BUILDER_VERSION = 1

logger = get_logger("cloud_pricing.history")

OpenSnapshot = Callable[["WeekSnapshot"], AbstractContextManager[ActiveSnapshot]]


@dataclass(frozen=True)
class WeekSnapshot:
    week: date  # the Monday of its ISO week
    snapshot_date: str
    revision: int
    manifest: Manifest = field(repr=False, compare=False)

    @property
    def label(self) -> str:
        return f"{self.snapshot_date} r{self.revision}"


def week_of(snapshot_date: str) -> date:
    day = date.fromisoformat(snapshot_date)
    return day - timedelta(days=day.weekday())


def select_weeks(manifests: Iterable[Manifest]) -> list[WeekSnapshot]:
    """One snapshot per ISO week: the latest succeeded date, at its latest revision."""
    best: dict[date, Manifest] = {}
    for manifest in manifests:
        if manifest.status != "succeeded" or manifest.purged is not None:
            continue
        week = week_of(manifest.snapshot_date)
        seen = best.get(week)
        if seen is None or (manifest.snapshot_date, manifest.revision) > (
            seen.snapshot_date, seen.revision
        ):
            best[week] = manifest
    return [
        WeekSnapshot(week, m.snapshot_date, m.revision, m) for week, m in sorted(best.items())
    ]


def gaps(weeks: Sequence[WeekSnapshot]) -> list[str]:
    """The Mondays of missing weeks between the first and last built week."""
    missing: list[str] = []
    for a, b in zip(weeks, weeks[1:], strict=False):
        day = a.week + timedelta(days=7)
        while day < b.week:
            missing.append(day.isoformat())
            day += timedelta(days=7)
    return missing


@dataclass
class BuildResult:
    weeks_total: int  # pairs the history should have
    weeks_built: int
    built: list[str]  # pairs (re)built in this run
    fetched: list[str]  # snapshots whose price lists were computed in this run


def _readable(path: Path) -> bool:
    try:
        with connect() as con:
            for name in ("counts.parquet", "changes.parquet"):
                con.execute(f"SELECT count(*) FROM read_parquet({_list([str(path / name)])})")
        return True
    except Exception:  # noqa: BLE001 — a missing or corrupt file means "rebuild this pair"
        return False


def _up_to_date(store: HistoryStore, a: WeekSnapshot, b: WeekSnapshot) -> bool:
    meta = store.pair_meta(a.snapshot_date, b.snapshot_date)
    return bool(
        meta
        and meta.get("from_snapshot") == a.label
        and meta.get("to_snapshot") == b.label
        and meta.get("builder_version") == BUILDER_VERSION
        and _readable(store.pair_dir(a.snapshot_date, b.snapshot_date))
    )


_PAIR_SQL = """
WITH a AS (SELECT * FROM read_parquet({a})),
     b AS (SELECT * FROM read_parquet({b})),
j AS (
    SELECT coalesce(b.location, a.location) AS location,
        coalesce(b.item_key, a.item_key) AS item_key,
        coalesce(b.service_key, a.service_key) AS service_key,
        coalesce(b.service_name, a.service_name) AS service_name,
        coalesce(b.description, a.description) AS description,
        coalesce(b.unit, a.unit) AS unit,
        coalesce(b.tiered, a.tiered) AS tiered,
        a.price AS old_price, b.price AS new_price,
        a.item_key IS NOT NULL AS in_old, b.item_key IS NOT NULL AS in_new,
        coalesce(a.price > 0 AND b.price > 0, false) AS ok
    FROM a FULL JOIN b ON a.location = b.location AND a.item_key = b.item_key
)
"""

_CHANGES = """
SELECT location, item_key, service_key, service_name, description, unit, tiered,
    old_price, new_price
FROM j WHERE ok AND new_price <> old_price
"""

_COUNTS = """
SELECT location, service_key,
    count(*) FILTER (WHERE ok) AS compared,
    count(*) FILTER (WHERE ok AND new_price = old_price) AS unchanged,
    count(*) FILTER (WHERE ok AND new_price > old_price) AS increased,
    count(*) FILTER (WHERE ok AND new_price < old_price) AS decreased,
    count(*) FILTER (WHERE NOT in_old) AS added,
    count(*) FILTER (WHERE NOT in_new) AS removed,
    count(*) FILTER (WHERE in_old AND in_new AND NOT ok) AS excluded
FROM j GROUP BY location, service_key
"""


def _quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def build_pair(
    store: HistoryStore, a: WeekSnapshot, b: WeekSnapshot, a_prices: Path, b_prices: Path
) -> Path:
    tmp = store.new_pair_tmp()
    try:
        with spilling(store.dir / ".duckdb-tmp") as con:
            head = _PAIR_SQL.format(a=_quote(a_prices), b=_quote(b_prices))
            for name, body in (("changes", _CHANGES), ("counts", _COUNTS)):
                con.execute(
                    f"COPY ({head} {body}) TO {_quote(tmp / f'{name}.parquet')} (FORMAT parquet)"
                )
        write_json(tmp / PAIR_FILE, {
            "from_snapshot": a.label,
            "to_snapshot": b.label,
            "from_date": a.snapshot_date,
            "to_date": b.snapshot_date,
            "from_week": a.week.isoformat(),
            "to_week": b.week.isoformat(),
            "gap": (b.week - a.week).days > 7,
            "built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "builder_version": BUILDER_VERSION,
        })
        return store.publish_pair(tmp, a.snapshot_date, b.snapshot_date)
    except BaseException:
        store.remove_pair(tmp)
        raise


def build_history(
    store: HistoryStore,
    weeks: Sequence[WeekSnapshot],
    write_prices: Callable[[ActiveSnapshot, Path], int],
    open_snapshot: OpenSnapshot,
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> BuildResult:
    """Bring `store` up to date with `weeks` (oldest first). `write_prices(snapshot, path)`
    writes a snapshot's comparable price list; `open_snapshot(week)` makes a snapshot readable
    for the duration of the `with` block (in place for `file://`, a verified copy for S3)."""
    store.clean_temporaries()
    state = store.state()
    if state.get("builder_version") not in (None, BUILDER_VERSION):
        store.clear()
    desired = list(zip(weeks, weeks[1:], strict=False))
    stale = {i for i, (a, b) in enumerate(desired) if not _up_to_date(store, a, b)}
    need = stale | {i + 1 for i in stale}
    built: list[str] = []
    fetched: list[str] = []
    processed: dict[str, int] = dict(state.get("processed", {}))

    def progress() -> None:
        done = len(desired) - len(stale)
        store.update_state(builder_version=BUILDER_VERSION, weeks_total=len(desired),
                           weeks_built=done, processed=processed)
        if on_progress:
            on_progress(done, len(desired))

    progress()
    prices: dict[int, Path] = {}
    for k, ws in enumerate(weeks):
        if k in need:
            path = store.prices_path(ws.snapshot_date, ws.revision)
            if not path.exists():
                tmp = path.with_name(f"{path.name}.tmp-{secrets.token_hex(4)}")
                with open_snapshot(ws) as snapshot:
                    write_prices(snapshot, tmp)
                tmp.rename(path)
                fetched.append(ws.label)
                processed[ws.snapshot_date] = ws.revision
            prices[k] = path
        if (k - 1) in stale:
            build_pair(store, weeks[k - 1], ws, prices[k - 1], prices[k])
            built.append(f"{weeks[k - 1].snapshot_date}_{ws.snapshot_date}")
            stale.discard(k - 1)
            progress()
        # Only the newest price list is kept, to diff against the next week.
        prices.pop(k - 1, None)
        # The newest week's list is kept too, so a rebuild in the middle doesn't refetch it.
        store.keep_only_prices(prices.get(k), _existing(store, weeks[-1]))

    # Pairs for weeks that no longer exist (e.g. a week whose snapshot was purged).
    wanted = {f"{a.snapshot_date}_{b.snapshot_date}" for a, b in desired}
    for path, _meta in store.pairs():
        if path.name not in wanted:
            store.remove_pair(path)
    newest = weeks[-1] if weeks else None
    store.keep_only_prices(_existing(store, newest) if newest else None)
    store.update_state(
        builder_version=BUILDER_VERSION, weeks_total=len(desired), weeks_built=len(desired),
        weeks=[w.label for w in weeks], gaps=gaps(weeks), processed=processed,
        last_built_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    if built:
        logger.info("price history built", provider=store.provider, pairs=built,
                    fetched=fetched)
    return BuildResult(len(desired), len(desired), built, fetched)


def _existing(store: HistoryStore, ws: WeekSnapshot | None) -> Path | None:
    if ws is None:
        return None
    path = store.prices_path(ws.snapshot_date, ws.revision)
    return path if path.exists() else None
