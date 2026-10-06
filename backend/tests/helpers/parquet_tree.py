"""Build fake pricing-data roots in the pipeline's storage layout for the snapshot tests
(018-app-cloud-deployment; `tests/fixtures/contracts/storage-layout.md`).

`make_pipeline_root` writes real data files (a tiny `service_dim` per region, and empty-schema
parquet for the other tables), `manifests/<D>/manifest.json` with real sha256 and byte sizes, and
optionally `manifests/latest.json`. Only what the app looks at is realistic; row contents beyond
`service_dim` don't matter to these tests.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from src.pricing_data.snapshot import TABLES

PROVIDER = "aws"


def run_id_for(snapshot_date: str, revision: int) -> str:
    """A contract-valid run id that differs per date and revision."""
    return f"{snapshot_date.replace('-', '')}T00000{revision % 10}Z-{revision:06x}"


def make_pipeline_root(root: Path, snapshots: list[dict]) -> Path:
    """Create a pipeline storage root under `root` with one manifest per snapshot spec.

    Per-snapshot keys (all optional except `date`):
    - `revision` (default 1), `status` (default "succeeded")
    - `regions` (default `["us-east-1"]`), `failed_regions` (`[(region, reason), ...]`)
    - `services`: `[(service_code, service_name), ...]` written to `service_dim`
    - `schema_versions`: `{table: version}` overrides (default 1 for all)
    - `extra_files`: `{table: n}` extra listed files per region (several files per region)
    - `unlisted_files`: `{table: n}` extra files written but NOT listed in the manifest
    - `bad_paths`: a list of raw path strings appended to `price_fact`'s first region
    - `point_latest` (default False): write `latest.json` naming this snapshot
    - `manifest_version` (default "1.0")
    """
    for spec in snapshots:
        _write_snapshot(root, spec)
    return root


def _write_snapshot(root: Path, spec: dict) -> None:
    snapshot_date = spec["date"]
    revision = spec.get("revision", 1)
    status = spec.get("status", "succeeded")
    regions = spec.get("regions", ["us-east-1"])
    failed = spec.get("failed_regions", [])
    services = spec.get("services", [("AmazonEC2", "Amazon Elastic Compute Cloud")])
    schema_versions = spec.get("schema_versions", {})
    extra_files = spec.get("extra_files", {})
    unlisted_files = spec.get("unlisted_files", {})
    run_id = run_id_for(snapshot_date, revision)

    tables: dict[str, dict] = {}
    if status != "purged":
        for table in TABLES:
            table_regions = {}
            total = 0
            for region in regions:
                files = []
                for n in range(1 + extra_files.get(table, 0)):
                    suffix = "" if n == 0 else f"-{n}"
                    key = _data_key(table, snapshot_date, region, run_id, suffix)
                    rows = _write_table(root / key, table, services)
                    files.append(_file_entry(root, key, rows))
                for n in range(unlisted_files.get(table, 0)):
                    stray = _data_key(table, snapshot_date, region, run_id, f"-{90 + n}")
                    _write_table(root / stray, table, services)
                rows = sum(f["row_count"] for f in files)
                table_regions[region] = {
                    "written_by_run": run_id,
                    "row_count": rows,
                    "files": files,
                }
                total += rows
            tables[table] = {
                "schema_version": schema_versions.get(table, 1),
                "row_count": total,
                "regions": table_regions,
            }
        if spec.get("bad_paths"):
            first = next(iter(tables["price_fact"]["regions"].values()))
            for path in spec["bad_paths"]:
                first["files"].append(
                    {"path": path, "bytes": 1, "sha256": "0" * 64, "row_count": 0}
                )

    stamp = f"{snapshot_date}T00:00:00Z"
    succeeded = [r for r in regions if r not in {f for f, _ in failed}]
    manifest = {
        "manifest_version": spec.get("manifest_version", "1.0"),
        "provider": PROVIDER,
        "snapshot_date": snapshot_date,
        "run_id": run_id,
        "revision": revision,
        "previous_revision": revision - 1 if revision > 1 else None,
        "created_at": stamp,
        "origin": "pipeline",
        "status": status,
        "regions": {
            "requested": regions,
            "succeeded": succeeded,
            "failed": [{"region": r, "reason": why, "attempts": 3} for r, why in failed],
        },
        "run": {
            "trigger": "scheduled",
            "mode": "full",
            "host": "aws-ecs",
            "started_at": stamp,
            "ended_at": stamp,
            "pipeline_version": {"git_sha": "abc1234", "image_tag": "abc1234"},
            "region_results": [],
        },
        "raw": None,
        "tables": tables,
        "purged": (
            {"purged_at": stamp, "reason": "retention-thinning"} if status == "purged" else None
        ),
    }
    manifest_key = f"{PROVIDER}/manifests/{snapshot_date}/manifest.json"
    (root / manifest_key).parent.mkdir(parents=True, exist_ok=True)
    (root / manifest_key).write_text(json.dumps(manifest, indent=2))

    if spec.get("point_latest"):
        latest = {
            "manifest_version": "1.0",
            "provider": PROVIDER,
            "snapshot_date": snapshot_date,
            "revision": revision,
            "run_id": run_id,
            "manifest_path": manifest_key,
            "updated_at": stamp,
        }
        (root / PROVIDER / "manifests" / "latest.json").write_text(json.dumps(latest))


def _data_key(table: str, snapshot_date: str, region: str, run_id: str, suffix: str) -> str:
    return (
        f"{PROVIDER}/parquet/{table}/snapshot_date={snapshot_date}/region={region}/"
        f"part-{run_id}{suffix}.parquet"
    )


def _write_table(dest: Path, table: str, services: list[tuple[str, str]]) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        if table == "service_dim":
            con.execute("CREATE TABLE s (service_code VARCHAR, service_name VARCHAR)")
            if services:
                con.executemany("INSERT INTO s VALUES (?, ?)", services)
            rows = len(services)
        else:
            con.execute("CREATE TABLE s (sku VARCHAR)")
            rows = 0
        con.execute(f"COPY s TO '{dest}' (FORMAT parquet)")
    finally:
        con.close()
    return rows


def _file_entry(root: Path, key: str, row_count: int) -> dict:
    data = (root / key).read_bytes()
    return {
        "path": key,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "row_count": row_count,
    }


# --- Legacy layout (016) — kept only until T096 removes the old-layout tests ------------------


def make_snapshot_tree(root: Path, dates: dict[str, dict]) -> Path:
    """The old `<table>/snapshot_date=<D>/region=<R>/` tree with `_SUCCESS` markers. Still used
    to build an *unsupported* old-layout directory for the "convert your data" message."""
    for date, options in dates.items():
        regions = options.get("regions", ["us-east-1"])
        services = options.get("services")
        for table in TABLES:
            date_dir = root / table / f"snapshot_date={date}"
            for region in regions:
                region_dir = date_dir / f"region={region}"
                region_dir.mkdir(parents=True, exist_ok=True)
                if table == "service_dim" and services is not None:
                    _write_table(region_dir / "part-0.parquet", table, services)
            if options.get("markers", True):
                (date_dir / "_SUCCESS").touch()
    return root
