"""Build the small Azure and GCP pricing fixtures used by the test suite (019, T004/T005).

The companion of `build_test_pricing_fixture.py` (AWS). It copies a few rows of one real snapshot
per provider into `tests/fixtures/pricing_parquet/<provider>/`, in the pipeline's storage layout
(`tests/fixtures/contracts/storage-layout.md`, manifest 1.1):

    <out>/<provider>/parquet/<table>/snapshot_date=<D>/region=<R>/part-<run_id>.parquet
    <out>/<provider>/manifests/<D>/manifest.json
    <out>/<provider>/manifests/latest.json

Rows are copied verbatim and in source order: nothing is fabricated or edited (Constitution
Principle I). DuckDB runs single-threaded so the order is the source scan order. The manifest is
the source manifest limited to the kept locations, with real `bytes`, `sha256` and `row_count`
for every written file. The expected prices are documented in each provider's README.md.

    uv run python scripts/build_provider_fixtures.py \
        --source-uri file:///path/to/DATA/pipeline [--provider azure|gcp]
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

import duckdb

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "pricing_parquet"

# --- What each fixture holds --------------------------------------------------------------------
# Per provider: the snapshot, the kept locations, and per location a WHERE clause on the
# provider's "item" table. The other tables follow the picked items (see `_build`).

AZURE_VM = (
    "arm_sku_name = 'Standard_D4s_v5' AND service_name = 'Virtual Machines'"
)  # Linux, Windows, Spot, Low Priority, Consumption, DevTest, Reservation 1/3 years
AZURE_EASTUS = " OR ".join(
    f"({c})"
    for c in (
        AZURE_VM,
        # Block storage, and the other product that repeats the meter name.
        "meter_name = 'P10 LRS Disk'",
        # Internet egress, both routes; first 100 GB tier is free (price 0).
        "service_name = 'Bandwidth' AND meter_name = 'Standard Data Transfer Out'",
        # Object storage, three tiers.
        "product_name = 'General Block Blob v2' AND meter_name = 'Hot LRS Data Stored'",
        # One item listed under two meter names with the same tier start and price (R8).
        "sku_id = 'DZH318Z0BPH7/006M' AND meter_id = '14854f12-8d37-4299-842a-b0f2df82a305'",
        # Managed relational DB.
        "product_name = 'Azure Database for PostgreSQL Flexible Server General Purpose Ddsv5 "
        "Series Compute' AND sku_name = '2 vCore'",
    )
)
AZURE = {
    "date": "2026-11-02",
    "item_table": "price_item",
    "locations": {
        "eastus": AZURE_EASTUS,
        # Global-only: one VM licence item (the data has no support plans).
        "global": "service_name = 'Virtual Machines Licenses' AND product_name = "
        "'SQL Server Standard' AND sku_name = '1-4 vCPU VM'",
        # Geography partition: Bandwidth Alliance only (never listed as a region).
        "north-america": "product_name = 'Bandwidth Alliance'",
    },
}

GCP_US_EAST1 = " OR ".join(
    f"({c})"
    for c in (
        # Every N2 on-demand core/RAM SKU, so the display-name filter is exercised; all
        # TYPE_MULTI_REGIONAL.
        "list_contains(product_taxonomy, 'VMs On Demand') AND list_contains(product_taxonomy, 'N2')",
        "display_name IN ('Balanced PD Capacity', 'Regional Balanced PD Capacity')",
        "display_name LIKE 'Standard Storage%'",
        "display_name = 'Network Internet Data Transfer Out from Americas to Americas'",
        "display_name IN ('Cloud SQL for PostgreSQL: Zonal - vCPU in Americas', "
        "'Cloud SQL for PostgreSQL: Zonal - RAM in Americas')",
    )
)
GCP = {
    "date": "2026-11-02",
    "item_table": "sku",
    "locations": {
        "us-east1": GCP_US_EAST1,
        "global": "sku_id = '92D2-8A8F-DF54'",  # Windows Server 2022 Datacenter licence on VM
    },
}

PROVIDERS = {"azure": AZURE, "gcp": GCP}


# --- Building -----------------------------------------------------------------------------------


def _copy(con: duckdb.DuckDBPyConnection, query: str, params: list, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({query}) TO '{dest}' (FORMAT parquet, COMPRESSION zstd)", params)
    return con.execute("SELECT count(*) FROM read_parquet(?)", [str(dest)]).fetchone()[0]


def _file_entry(out: Path, key: str, row_count: int) -> dict:
    data = (out / key).read_bytes()
    return {
        "path": key,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "row_count": row_count,
    }


def _build(provider: str, source_root: Path, out: Path) -> None:
    spec = PROVIDERS[provider]
    snapshot_date = spec["date"]
    source_manifest = json.loads(
        (source_root / provider / "manifests" / snapshot_date / "manifest.json").read_text()
    )
    if source_manifest["status"] != "succeeded":
        raise SystemExit(f"{provider} {snapshot_date}: status is {source_manifest['status']}")
    run_id = source_manifest["run_id"]
    locations = list(spec["locations"])
    dest_root = out / provider
    if dest_root.exists():
        shutil.rmtree(dest_root)

    con = duckdb.connect(config={"threads": 1})

    def source_files(table: str, location: str) -> list[str]:
        entry = source_manifest["tables"][table]["regions"][location]
        return [str(source_root / f["path"]) for f in entry["files"]]

    def key_for(table: str, location: str) -> str:
        return (
            f"{provider}/parquet/{table}/snapshot_date={snapshot_date}/region={location}/"
            f"part-{run_id}.parquet"
        )

    tables: dict[str, dict] = {
        name: {"schema_version": t["schema_version"], "row_count": 0, "regions": {}}
        for name, t in source_manifest["tables"].items()
    }

    def record(table: str, location: str, query: str | None, params: list) -> None:
        entry = {"written_by_run": run_id, "row_count": 0, "files": []}
        if query is not None:
            key = key_for(table, location)
            rows = _copy(con, query, params, out / key)
            entry["row_count"] = rows
            entry["files"] = [_file_entry(out, key, rows)]
            tables[table]["row_count"] += rows
        tables[table]["regions"][location] = entry

    item_table = spec["item_table"]
    service_ids: set[str] = set()
    for location, where in spec["locations"].items():
        src = source_files(item_table, location)
        record(item_table, location, f"SELECT * FROM read_parquet(?) WHERE {where}", [src])
        picked = out / key_for(item_table, location)
        if provider == "azure":
            keys = [r[0] for r in con.execute(
                "SELECT price_item_key FROM read_parquet(?)", [str(picked)]
            ).fetchall()]
            record(
                "price_item_savings_plan",
                location,
                "SELECT * FROM read_parquet(?) WHERE price_item_key IN (SELECT unnest(?::VARCHAR[]))",
                [source_files("price_item_savings_plan", location), keys],
            )
        else:
            skus = [r[0] for r in con.execute(
                "SELECT sku_id FROM read_parquet(?)", [str(picked)]
            ).fetchall()]
            service_ids |= {r[0] for r in con.execute(
                "SELECT DISTINCT service_id FROM read_parquet(?)", [str(picked)]
            ).fetchall()}
            for table in ("sku_price", "sku_price_tier"):
                record(
                    table,
                    location,
                    "SELECT * FROM read_parquet(?) WHERE sku_id IN (SELECT unnest(?::VARCHAR[]))",
                    [source_files(table, location), skus],
                )
        print(f"{provider} {location}: {tables[item_table]['regions'][location]['row_count']} "
              f"{item_table} rows")

    if provider == "gcp":
        # `service` lives in the global partition only; other locations list no files.
        for location in locations:
            if location == "global":
                record(
                    "service",
                    location,
                    "SELECT * FROM read_parquet(?) WHERE service_id IN (SELECT unnest(?::VARCHAR[]))",
                    [source_files("service", "global"), sorted(service_ids)],
                )
            else:
                record("service", location, None, [])

    manifest = copy.deepcopy(source_manifest)
    manifest["regions"] = {"requested": locations, "succeeded": locations, "failed": []}
    manifest["run"]["region_results"] = [
        r for r in manifest["run"].get("region_results", []) if r["region"] in locations
    ]
    manifest["tables"] = tables
    manifest_key = f"{provider}/manifests/{snapshot_date}/manifest.json"
    (out / manifest_key).parent.mkdir(parents=True, exist_ok=True)
    (out / manifest_key).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    latest = json.loads((source_root / provider / "manifests" / "latest.json").read_text())
    latest.update(
        snapshot_date=snapshot_date,
        revision=manifest["revision"],
        run_id=run_id,
        manifest_path=manifest_key,
    )
    (out / provider / "manifests" / "latest.json").write_text(
        json.dumps(latest, indent=2, sort_keys=True) + "\n"
    )
    print(f"wrote {provider} snapshot {snapshot_date} to {dest_root}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-uri", required=True, help="file:// pipeline storage root")
    parser.add_argument("--provider", choices=sorted(PROVIDERS), action="append")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    parsed = urlparse(args.source_uri)
    if parsed.scheme != "file":
        raise SystemExit("--source-uri must be a file:// pipeline storage root")
    for provider in args.provider or sorted(PROVIDERS):
        _build(provider, Path(parsed.path), args.out)


if __name__ == "__main__":
    main()
