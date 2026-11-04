"""Comparable price lists for Trends (019, research R10).

One row per (location, item) of a snapshot: its on-demand price on the **first non-zero tier**
(so a free first tier doesn't hide a change), as published. A price that is null on any tier is
null (not published); a price that is 0 on every tier is 0. Both are kept so the history builder
counts them as excluded.

Each adapter supplies one SQL query over its own tables (as DuckDB views); this module runs it
and writes the result as Parquet, so a whole AWS snapshot never sits in Python memory.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from src.pricing_data.duckdb_conn import connect, spilling
from src.pricing_data.providers._sql import _list
from src.pricing_data.providers.base import ComparablePrice
from src.pricing_data.snapshot import ActiveSnapshot

COLUMNS = ("location", "item_key", "service_key", "service_name", "description", "unit",
           "price", "tiered")
PRICE_TYPE = "DECIMAL(38, 12)"


def all_files(snapshot: ActiveSnapshot, table: str) -> list[str]:
    return [f for loc in sorted(snapshot.regions(table)) for f in snapshot.files(table, loc)]


def write(snapshot: ActiveSnapshot, tables: tuple[str, ...], query: str, out: Path) -> int:
    """Run `query` over views of every location's files of `tables`; write Parquet to `out`.
    Returns the row count."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with spilling(out.parent / ".duckdb-tmp") as con:
        for table in tables:
            files = all_files(snapshot, table)
            if not files:
                raise FileNotFoundError(f"snapshot has no {table} files")
            con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet({_list(files)}, "
                        "union_by_name = true)")
        select = ", ".join(COLUMNS)
        con.execute(
            f"COPY (SELECT {select} FROM ({query})) "
            f"TO '{str(out).replace(chr(39), chr(39) * 2)}' (FORMAT parquet)"
        )
        return con.execute(f"SELECT count(*) FROM read_parquet({_list([str(out)])})").fetchone()[0]


def plain(value: Decimal) -> Decimal:
    """Trailing zeros removed, never in exponent form (`20`, not `2E+1`)."""
    value = value.normalize()
    return value.quantize(Decimal(1)) if value.as_tuple().exponent > 0 else value


def read(path: Path) -> list[ComparablePrice]:
    with connect() as con:
        rows = con.execute(
            f"SELECT {', '.join(COLUMNS)} FROM read_parquet({_list([str(path)])}) "
            "ORDER BY location, item_key"
        ).fetchall()
    return [
        ComparablePrice(location=r[0], item_key=r[1], service_key=r[2], service_name=r[3],
                        description=r[4], unit=r[5],
                        price=None if r[6] is None else plain(Decimal(r[6])),
                        tiered=bool(r[7]))
        for r in rows
    ]


# The first non-zero tier's price, ordered by tier start (`start`); 0 when every tier is 0;
# null when any tier's price is null. `tiered` when there is more than one tier.
def first_nonzero(price: str, start: str) -> str:
    return (
        f"CASE WHEN bool_or({price} IS NULL) THEN NULL "
        f"ELSE coalesce(arg_min({price}, {start}) FILTER (WHERE {price} <> 0), 0) "
        f"END::{PRICE_TYPE}"
    )


class ComparableMixin:
    """`write_comparable_prices` / `comparable_prices` from the adapter's `_comparable_sql()`
    over its `comparable_tables`."""

    comparable_tables: tuple[str, ...]

    def _comparable_sql(self) -> str:  # pragma: no cover - each adapter defines it
        raise NotImplementedError

    def write_comparable_prices(self, snapshot: ActiveSnapshot, out: Path) -> int:
        return write(snapshot, self.comparable_tables, self._comparable_sql(), out)

    def comparable_prices(self, snapshot: ActiveSnapshot) -> list[ComparablePrice]:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prices.parquet"
            self.write_comparable_prices(snapshot, path)
            return read(path)
