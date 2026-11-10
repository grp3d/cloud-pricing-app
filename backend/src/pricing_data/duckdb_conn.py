"""DuckDB connections for the pricing queries (018-app-cloud-deployment, research.md R3).

Every connection is capped by `DUCKDB_MEMORY_LIMIT` and `DUCKDB_THREADS`, so pricing fits beside
Postgres on a 2 GiB instance. Connections are in-memory and short-lived: one per query.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

from src.config import settings
from src.pricing_data.errors import PricingDataUnavailableError
from src.pricing_data.snapshot import ActiveSnapshot


def connect(*, spill_dir: Path | None = None) -> duckdb.DuckDBPyConnection:
    """`spill_dir` (019, price history): large batch jobs may spill to disk there instead of
    failing at `DUCKDB_MEMORY_LIMIT`; row order is not kept, which they don't need."""
    config: dict[str, object] = {
        "memory_limit": settings.duckdb_memory_limit, "threads": settings.duckdb_threads,
    }
    if spill_dir is not None:
        spill_dir.mkdir(parents=True, exist_ok=True)
        config.update(temp_directory=str(spill_dir), preserve_insertion_order=False)
    return duckdb.connect(":memory:", config=config)


@contextmanager
def spilling(spill_dir: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    """A `connect(spill_dir=...)` connection whose spill folder is removed afterwards."""
    con = connect(spill_dir=spill_dir)
    try:
        yield con
    finally:
        con.close()
        shutil.rmtree(spill_dir, ignore_errors=True)


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
