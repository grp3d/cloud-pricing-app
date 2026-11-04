"""Trends metrics from the price history (019, research R10, R11, data-model §8).

**SKUs Changed** for one week pair: increased and decreased, summed from `counts` over the
selected locations and the category's service keys, with compared and excluded for the hover,
and each as a % of compared. A week with nothing compared has null counts ("no data"); a week
with no changes is 0 up and 0 down.

Locations: no regions selected means every location of the provider. When regions are selected,
`global` is added, so a global-only item counts once per provider (spec Edge Cases). A
multi-regional item is filed under each member region, so it counts once per selected region.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from src.pricing_data.duckdb_conn import connect
from src.pricing_data.history.store import HistoryStore
from src.pricing_data.providers._sql import _list
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
