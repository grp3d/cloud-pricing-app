"""Trends metrics from the price history (019, research R10, R11, data-model §8).

**SKUs Changed** for one week pair: increased and decreased, summed from `counts` over the
selected locations and the category's service keys, with compared and excluded for the hover,
and each as a % of compared. A week with nothing compared has null counts ("no data"); a week
with no changes is 0 up and 0 down.

Locations: no regions selected means every location of the provider. When regions are selected,
`global` is added, so a global-only item counts once per provider (spec Edge Cases). A
multi-regional item is filed under each member region, so it counts once per selected region.

**Price movers** for a period: the pairs that overlap the newest `period_weeks` weeks. Per
(location, item): the start price is the old price of its first change in the window, the end
price its price in the newest price list (so an item removed or no longer validly priced at the
end is dropped), and items whose end price equals the start are dropped. The 3 largest %
increases and decreases, ties ranked by the size of the price change, then by name.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from src.pricing_data.duckdb_conn import connect
from src.pricing_data.history.store import HistoryStore
from src.pricing_data.providers._sql import _list
from src.pricing_data.providers.comparable import plain
from src.pricing_data.snapshot import GLOBAL

MAX_WEEKS = 52

KeyFilter = Callable[[set[str]], set[str]]


@dataclass(frozen=True)
class SkusChangedPoint:
    week: str
    from_snapshot: str
    to_snapshot: str
    increased: int | None
    decreased: int | None
    increased_pct: float | None
    decreased_pct: float | None
    compared: int | None
    excluded: int | None
    gap: bool


def locations_for(regions: list[str]) -> list[str] | None:
    """None means every location."""
    return None if not regions else sorted({*regions, GLOBAL})


def _pct(part: int, whole: int) -> float:
    return float(Decimal(part) * 100 / Decimal(whole))


def skus_changed(
    store: HistoryStore,
    *,
    regions: list[str],
    keys: KeyFilter | None = None,
    weeks: int = MAX_WEEKS,
) -> list[SkusChangedPoint]:
    """One point per built week pair, oldest first, the newest `weeks` (at most 52).
    `keys(all_keys)` narrows the service keys to a category; None keeps all of them."""
    pairs = store.pairs()[-min(weeks, MAX_WEEKS):] if weeks > 0 else []
    if not pairs:
        return []
    files = [str(path / "counts.parquet") for path, _meta in pairs]
    locations = locations_for(regions)
    with connect() as con:
        con.execute(f"CREATE VIEW counts AS SELECT * FROM read_parquet({_list(files)}, "
                    "filename = true)")
        where, params = ["true"], []
        if locations is not None:
            where.append("list_contains(?, location)")
            params.append(locations)
        if keys is not None:
            present = {r[0] for r in con.execute(
                "SELECT DISTINCT service_key FROM counts").fetchall()}
            where.append("list_contains(?, service_key)")
            params.append(sorted(keys(present)))
        rows = con.execute(
            "SELECT filename, sum(compared), sum(increased), sum(decreased), sum(excluded) "
            f"FROM counts WHERE {' AND '.join(where)} GROUP BY filename",
            params,
        ).fetchall()
    sums = {r[0]: tuple(int(x or 0) for x in r[1:]) for r in rows}
    points = []
    for path, meta in pairs:
        compared, increased, decreased, excluded = sums.get(
            str(path / "counts.parquet"), (0, 0, 0, 0))
        has_data = compared > 0
        points.append(SkusChangedPoint(
            week=meta["to_date"],
            from_snapshot=meta["from_snapshot"],
            to_snapshot=meta["to_snapshot"],
            increased=increased if has_data else None,
            decreased=decreased if has_data else None,
            increased_pct=_pct(increased, compared) if has_data else None,
            decreased_pct=_pct(decreased, compared) if has_data else None,
            compared=compared if has_data else None,
            excluded=excluded if has_data else None,
            gap=bool(meta.get("gap")),
        ))
    return points


MOVERS_LIMIT = 3
TIER_NOTE = "Compared on the first non-zero tier"


@dataclass(frozen=True)
class Mover:
    item_key: str
    service_name: str
    description: str
    region: str
    unit: str
    start_price: Decimal
    end_price: Decimal
    change_pct: float
    tier_note: str | None


@dataclass(frozen=True)
class MoversResult:
    from_snapshot: str
    to_snapshot: str
    weeks_available: int
    increases: list[Mover]
    decreases: list[Mover]


def _week(meta: dict[str, Any], side: str) -> date:
    stored = meta.get(f"{side}_week")
    if stored:
        return date.fromisoformat(stored)
    day = date.fromisoformat(meta[f"{side}_date"])
    return day - timedelta(days=day.weekday())


def _newest_prices(store: HistoryStore, to_snapshot: str) -> Path | None:
    snapshot_date, _sep, rev = to_snapshot.partition(" r")
    path = store.prices_path(snapshot_date, int(rev or 1))
    return path if path.exists() else None


def movers(
    store: HistoryStore,
    *,
    regions: list[str],
    keys: KeyFilter | None = None,
    period_weeks: int = MAX_WEEKS,
    limit: int = MOVERS_LIMIT,
) -> MoversResult | None:
    """None when there is no built week pair yet."""
    pairs = store.pairs()
    if not pairs:
        return None
    end_week = _week(pairs[-1][1], "to")
    start = end_week - timedelta(weeks=period_weeks)
    window = [(path, meta) for path, meta in pairs if _week(meta, "to") > start]
    first_week = max(_week(window[0][1], "from"), start)
    from_snapshot = window[0][1]["from_snapshot"]
    to_snapshot = window[-1][1]["to_snapshot"]
    files = [str(path / "changes.parquet") for path, _meta in window]
    order = {f: i for i, f in enumerate(files)}
    newest = _newest_prices(store, to_snapshot)
    locations = locations_for(regions)
    with connect() as con:
        con.execute(f"CREATE VIEW changes AS SELECT * FROM read_parquet({_list(files)}, "
                    "filename = true)")
        where, params = ["true"], []
        if locations is not None:
            where.append("list_contains(?, location)")
            params.append(locations)
        if keys is not None:
            present = {r[0] for r in con.execute(
                "SELECT DISTINCT service_key FROM changes").fetchall()}
            where.append("list_contains(?, service_key)")
            params.append(sorted(keys(present)))
        rows = con.execute(
            "SELECT filename, location, item_key, service_name, description, unit, tiered, "
            f"old_price, new_price FROM changes WHERE {' AND '.join(where)}",
            params,
        ).fetchall()
        ends: dict[tuple[str, str], tuple] | None = None
        if newest is not None and rows:
            ends = {(r[0], r[1]): r[2:] for r in con.execute(
                "SELECT location, item_key, service_name, description, unit, tiered, price "
                f"FROM read_parquet({_list([str(newest)])}) WHERE price > 0").fetchall()}
    # Per (location, item): the first change's row and the last change's row in the window.
    first: dict[tuple[str, str], tuple] = {}
    last: dict[tuple[str, str], tuple] = {}
    for row in sorted(rows, key=lambda r: order[r[0]]):
        key = (row[1], row[2])
        first.setdefault(key, row)
        last[key] = row
    entries: list[tuple[Decimal, Mover]] = []
    for key, row in first.items():
        start_price = Decimal(row[7])
        if ends is None:  # no newest price list kept: the last change's new price
            tail = last[key]
            name, description, unit, tiered, end_value = tail[3], tail[4], tail[5], tail[6], tail[8]
        else:
            if key not in ends:
                continue  # removed, or no valid price, at the end
            name, description, unit, tiered, end_value = ends[key]
        end_price = Decimal(end_value)
        if end_price == start_price or start_price <= 0:
            continue
        pct = (end_price - start_price) * 100 / start_price
        entries.append((pct, Mover(
            item_key=key[1], service_name=name or "", description=description or "",
            region=key[0], unit=unit or "", start_price=plain(start_price),
            end_price=plain(end_price),
            change_pct=float(pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            tier_note=TIER_NOTE if tiered else None,
        )))

    def ranked(items: list[tuple[Decimal, Mover]]) -> list[Mover]:
        items.sort(key=lambda e: (-abs(e[0]), -abs(e[1].end_price - e[1].start_price),
                                  e[1].service_name, e[1].description, e[1].region))
        return [m for _pct, m in items[:limit]]

    return MoversResult(
        from_snapshot=from_snapshot,
        to_snapshot=to_snapshot,
        weeks_available=(end_week - first_week).days // 7,
        increases=ranked([e for e in entries if e[0] > 0]),
        decreases=ranked([e for e in entries if e[0] < 0]),
    )
