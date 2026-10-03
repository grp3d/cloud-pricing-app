"""DuckDB connections for the pricing queries (018-app-cloud-deployment, research.md R3).

Every connection is capped by `DUCKDB_MEMORY_LIMIT` and `DUCKDB_THREADS`, so pricing fits beside
Postgres on a 2 GiB instance. Connections are in-memory and short-lived: one per query.
"""

from __future__ import annotations

import duckdb

from src.config import settings
from src.pricing_data.errors import PricingDataUnavailableError
from src.pricing_data.snapshot import ActiveSnapshot


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(
        ":memory:",
        config={"memory_limit": settings.duckdb_memory_limit, "threads": settings.duckdb_threads},
    )


def table_files(snapshot: ActiveSnapshot, table: str, region: str) -> list[str]:
    """The snapshot's files for one table and region; no files is the same "pricing data
    unavailable" error a missing partition always produced."""
    files = snapshot.files(table, region)
    if not files:
        raise PricingDataUnavailableError(
            f"snapshot {snapshot.snapshot_date} r{snapshot.revision} has no {table} data for "
            f"region {region}"
        )
    return files
