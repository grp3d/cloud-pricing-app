"""Price history helpers for the 019 Trends tests."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from src.pricing_data.history.builder import build_history, select_weeks
from src.pricing_data.history.source import list_manifests, snapshot_opener
from src.pricing_data.history.store import HistoryStore
from src.pricing_data.providers.comparable import COLUMNS
from src.pricing_data.providers.registry import get_provider
from src.pricing_data.storage import LocalStore

CHANGE_COLUMNS = ("location, item_key, service_key, service_name, description, unit, tiered, "
                  "old_price, new_price")
TRENDS_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "trends"


def build_trends_history(history_dir: Path, root: Path = TRENDS_ROOT) -> HistoryStore:
    """The T007 fixture's AWS history, built into `history_dir`."""
    store = HistoryStore(history_dir, "aws")
    source = LocalStore(root)
    aws = get_provider("aws")
    build_history(store, select_weeks(list_manifests(source, "aws")),
                  aws.write_comparable_prices, snapshot_opener(source, aws.comparable_tables))
    store.update_state(backfill="done", last_error=None)
    return store


def _sql(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str) and not value.replace(".", "", 1).isdigit():
        return "'" + value.replace("'", "''") + "'"
    return f"CAST({value} AS DECIMAL(38, 12))"


def _copy(rows: list[tuple], columns: str, out: Path) -> None:
    values = ", ".join("(" + ", ".join(_sql(v) for v in row) + ")" for row in rows)
    duckdb.sql(f"COPY (SELECT * FROM (VALUES {values}) t({columns})) TO '{out}' (FORMAT parquet)")


def write_prices(store: HistoryStore, snapshot_date: str, rows: list[tuple],
                 revision: int = 1) -> None:
    """A hand-made newest price list. Rows: (location, item_key, service_key, service_name,
    description, unit, price, tiered); prices as strings, e.g. "0.10"."""
    store.prices_dir.mkdir(parents=True, exist_ok=True)
    for path in store.prices_dir.glob("*.parquet"):
        path.unlink()
    _copy(rows, ", ".join(COLUMNS), store.prices_path(snapshot_date, revision))


def write_pair(store: HistoryStore, from_date: str, to_date: str, counts: list[tuple],
               *, gap: bool = False, changes: list[tuple] | None = None) -> None:
    """A hand-made pair. `counts` rows: (location, service_key, compared, increased, decreased,
    excluded). `changes` rows: (location, item_key, service_key, service_name, description,
    unit, tiered, old_price, new_price), prices as strings."""
    path = store.pair_dir(from_date, to_date)
    path.mkdir(parents=True, exist_ok=True)
    rows = ", ".join(
        f"('{loc}', '{key}', {c}, {c - i - d}, {i}, {d}, 0, 0, {e})"
        for loc, key, c, i, d, e in counts
    ) or "('x', 'x', 0, 0, 0, 0, 0, 0, 0)"
    duckdb.sql(
        f"COPY (SELECT * FROM (VALUES {rows}) t(location, service_key, compared, unchanged, "
        "increased, decreased, added, removed, excluded)) "
        f"TO '{path / 'counts.parquet'}' (FORMAT parquet)"
    )
    if changes:
        _copy(changes, CHANGE_COLUMNS, path / "changes.parquet")
    else:
        duckdb.sql(
            "COPY (SELECT 'x' AS location, 'x' AS item_key, 'x' AS service_key, "
            "'x' AS service_name, 'x' AS description, 'x' AS unit, false AS tiered, "
            "1.0::DECIMAL(38, 12) AS old_price, 2.0::DECIMAL(38, 12) AS new_price "
            f"WHERE false) TO '{path / 'changes.parquet'}' (FORMAT parquet)"
        )
    (path / "pair.json").write_text(json.dumps({
        "from_snapshot": f"{from_date} r1", "to_snapshot": f"{to_date} r1",
        "from_date": from_date, "to_date": to_date, "gap": gap, "builder_version": 1,
        "built_at": "2026-11-04T00:00:00Z",
    }))
