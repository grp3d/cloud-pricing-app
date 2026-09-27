"""Build fake pricing-data folder trees for the active-snapshot and icon-coverage tests
(016-canvas-icon-layout). Only the layout the snapshot monitor looks at is real — the five table
folders, `snapshot_date=`/`region=` partitions, and `_SUCCESS` markers — plus, optionally, a tiny
`service_dim` parquet with the service codes and names the icon analysis reads.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from src.pricing_data.snapshot import TABLES


def make_snapshot_tree(root: Path, dates: dict[str, dict]) -> Path:
    """Create `root/<table>/snapshot_date=<date>/region=<region>/` for each date.

    Per-date options (all optional):
    - `regions`: region names (default `["us-east-1"]`)
    - `tables_missing`: tables that don't get this date at all
    - `markers_missing`: tables that get the date but no `_SUCCESS`
    - `markers`: False to write no `_SUCCESS` anywhere (default True)
    - `services`: `[(service_code, service_name), ...]` written to `service_dim` in each region
    """
    for date, options in dates.items():
        regions = options.get("regions", ["us-east-1"])
        tables_missing = set(options.get("tables_missing", ()))
        markers_missing = set(options.get("markers_missing", ()))
        write_markers = options.get("markers", True)
        services = options.get("services")
        for table in TABLES:
            if table in tables_missing:
                continue
            date_dir = root / table / f"snapshot_date={date}"
            for region in regions:
                region_dir = date_dir / f"region={region}"
                region_dir.mkdir(parents=True, exist_ok=True)
                if table == "service_dim" and services is not None:
                    _write_service_dim(region_dir / "part-0.parquet", services)
            date_dir.mkdir(parents=True, exist_ok=True)
            if write_markers and table not in markers_missing:
                (date_dir / "_SUCCESS").touch()
    return root


def _write_service_dim(dest: Path, services: list[tuple[str, str]]) -> None:
    con = duckdb.connect()
    con.execute("CREATE TABLE s (service_code VARCHAR, service_name VARCHAR)")
    if services:
        con.executemany("INSERT INTO s VALUES (?, ?)", services)
    con.execute(f"COPY s TO '{dest}' (FORMAT parquet)")
