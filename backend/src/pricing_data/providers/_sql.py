"""Small DuckDB helpers shared by the Azure and GCP adapters (019)."""

from __future__ import annotations

from collections.abc import Sequence

import duckdb

from src.pricing_data.catalog import InvalidRegexPatternError
from src.pricing_data.duckdb_conn import connect
from src.pricing_data.errors import PricingDataUnavailableError
from src.pricing_data.snapshot import ActiveSnapshot


def open_views(
    snapshot: ActiveSnapshot, region: str, tables: Sequence[str], *, required: str
) -> duckdb.DuckDBPyConnection:
    """A connection with one view per table over `region`'s files plus `global`'s (research R5).

    A table with no files for the location (an Azure savings-plan partition with no rows is
    still listed, but a GCP `service` table lists only `global`) becomes an empty view with the
    same columns, read from any other location's file. `required` names the table that must
    have files: without it the snapshot holds nothing for this location, which is "pricing data
    unavailable" (503), never an empty result.
    """
    con = connect()
    for table in tables:
        files = snapshot.files_with_global(table, region)
        if files:
            con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet({_list(files)})")
            continue
        if table == required:
            con.close()
            raise PricingDataUnavailableError(
                f"snapshot {snapshot.snapshot_date} r{snapshot.revision} has no {table} data "
                f"for location {region}",
                snapshot.provider,
            )
        any_files = [f for loc in sorted(snapshot.regions(table)) for f in snapshot.files(table, loc)]
        if not any_files:
            con.close()
            raise PricingDataUnavailableError(
                f"snapshot {snapshot.snapshot_date} r{snapshot.revision} has no {table} files",
                snapshot.provider,
            )
        con.execute(
            f"CREATE VIEW {table} AS SELECT * FROM read_parquet({_list(any_files[:1])}) "
            "WHERE false"
        )
    return con


def _list(paths: Sequence[str]) -> str:
    """A SQL list literal of file paths (a view can't take bound parameters). The paths come
    from the verified manifest; quotes are escaped all the same."""
    return "[" + ", ".join("'" + p.replace("'", "''") + "'" for p in paths) + "]"


def check_patterns(con: duckdb.DuckDBPyConnection, patterns: dict[str, str | None]) -> None:
    """Every filter is a case-insensitive RE2 pattern, as for AWS (008 research §2). A malformed
    one raises `InvalidRegexPatternError` naming its field (→ 400)."""
    for name, pattern in patterns.items():
        if not pattern:
            continue
        try:
            con.execute("SELECT regexp_matches('', ?, 'i')", [pattern])
        except duckdb.Error as exc:
            raise InvalidRegexPatternError(name, str(exc)) from exc
