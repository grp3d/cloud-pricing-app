"""Build the multi-week Trends fixture (019, T007): `tests/fixtures/trends/`.

**Synthetic data.** Real list prices change too rarely (research R11: about 1 change in 122,000
SKUs over 3 weeks) to give a small fixture every case the history builder must handle, so this
fixture is made up: invented SKUs and prices in the real AWS table schemas and the pipeline's
storage layout (manifest 1.0, `revisions/`, real `bytes`/`sha256`/`row_count`). It is only ever
read by tests. The cases and their expected counts are documented in
`tests/fixtures/trends/README.md`; re-run after changing `PRICES`:

    uv run python scripts/build_trends_fixture.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import duckdb

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "trends"
PROVIDER = "aws"
TABLES = ("service_dim", "product_dim", "product_attribute", "region_dim", "price_fact")

# Weekly snapshot dates; 2026-09-28 is deliberately missing (a gap).
WEEKS = ("2026-09-07", "2026-09-14", "2026-09-21", "2026-10-05", "2026-10-12")
REVISED = "2026-09-21"  # also published as revision 2

LOCATIONS = {
    "us-east-1": "US East (N. Virginia)",
    "us-west-2": "US West (Oregon)",
}
SERVICES = {
    "AmazonEC2": ("Amazon Elastic Compute Cloud", "Compute Instance", "Hrs"),
    "AmazonS3": ("Amazon Simple Storage Service", "Storage", "GB-Mo"),
    "AWSDataTransfer": ("AWS Data Transfer", "Data Transfer", "GB"),
}

# (location, sku, service_code) -> on-demand price per week, in WEEKS order.
# None = SKU absent that week; "null" = row present with a null price; a list = tiers
# [(begin, end, price), ...]. REVISED week: (revision 1 value, revision 2 value).
PRICES: dict[tuple[str, str, str], tuple] = {
    ("us-east-1", "TRDRISE000000001", "AmazonEC2"): (0.10, 0.10, (0.10, 0.11), 0.11, 0.11),
    ("us-east-1", "TRDFALL000000001", "AmazonEC2"): (0.20, 0.18, 0.18, 0.18, 0.18),
    ("us-east-1", "TRDBACK000000001", "AmazonEC2"): (0.30, 0.30, 0.33, 0.30, 0.30),
    ("us-east-1", "TRDADDED00000001", "AmazonS3"): (None, None, 0.05, 0.05, 0.05),
    ("us-east-1", "TRDREMOVED000001", "AmazonS3"): (0.04, 0.04, 0.04, None, None),
    ("us-east-1", "TRDZERO000000001", "AmazonEC2"): (0.50, 0.0, 0.50, 0.50, 0.50),
    ("us-east-1", "TRDNULL000000001", "AmazonEC2"): (0.60, 0.60, 0.60, "null", 0.60),
    ("us-east-1", "TRDTIER000000001", "AWSDataTransfer"): (
        [("0", "1", 0.0), ("1", "Inf", 0.09)],
        [("0", "1", 0.0), ("1", "Inf", 0.09)],
        [("0", "1", 0.0), ("1", "Inf", 0.09)],
        [("0", "1", 0.0), ("1", "Inf", 0.09)],
        [("0", "1", 0.0), ("1", "Inf", 0.085)],
    ),
    ("us-east-1", "TRDSTABLE0000001", "AmazonEC2"): (0.07, 0.07, 0.07, 0.07, 0.07),
    ("us-east-1", "TRDSTABLE0000002", "AmazonS3"): (0.023, 0.023, 0.023, 0.023, 0.023),
    ("us-west-2", "TRDW2RISE0000001", "AmazonEC2"): (0.12, 0.12, 0.12, 0.12, 0.13),
    ("us-west-2", "TRDW2STABLE00001", "AmazonEC2"): (0.08, 0.08, 0.08, 0.08, 0.08),
}
# A reserved price that changes every week: never counted (on-demand only).
RESERVED = ("us-east-1", "TRDRISE000000001", (500.0, 600.0, 700.0, 800.0, 900.0))


def run_id_for(snapshot_date: str, revision: int) -> str:
    return f"{snapshot_date.replace('-', '')}T00000{revision}Z-{revision:06x}"


def _value(week_index: int, raw, revision: int):
    if isinstance(raw, tuple) and WEEKS[week_index] == REVISED:
        return raw[revision - 1]
    return raw


def _write(con, dest: Path, sql: str, rows: list[tuple]) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    con.execute("DROP TABLE IF EXISTS t")
    con.execute(f"CREATE TABLE t ({sql})")
    if rows:
        placeholders = ", ".join("?" for _ in rows[0])
        con.executemany(f"INSERT INTO t VALUES ({placeholders})", rows)
    con.execute(f"COPY t TO '{dest}' (FORMAT parquet, COMPRESSION zstd)")
    return len(rows)


def _rows(snapshot_date: str, week_index: int, revision: int, location: str) -> dict[str, list]:
    region_name = LOCATIONS[location]
    rows: dict[str, list] = {t: [] for t in TABLES}
    rows["service_dim"] = [
        (snapshot_date, code, name, code, f"{snapshot_date}T00:00:00Z", location)
        for code, (name, _, _) in SERVICES.items()
    ]
    rows["region_dim"] = [(snapshot_date, location, region_name, "AWS Region", location)]
    for (loc, sku, service), weekly in PRICES.items():
        if loc != location:
            continue
        value = _value(week_index, weekly[week_index], revision)
        if value is None:
            continue
        _, family, unit = SERVICES[service]
        attributes = {
            "servicecode": service,
            "location": region_name,
            "locationType": "AWS Region",
            "regionCode": location,
            "usagetype": f"TRD-{sku[3:9]}",
        }
        rows["product_dim"].append(
            (snapshot_date, sku, service, location, family, json.dumps(attributes), location)
        )
        rows["product_attribute"] += [
            (snapshot_date, sku, service, k, v, location) for k, v in attributes.items()
        ]
        tiers = value if isinstance(value, list) else [("0", "Inf", value)]
        for begin, end, price in tiers:
            price = None if price == "null" else price
            text = "no price" if price is None else f"${price} per {unit}"
            rows["price_fact"].append(
                (snapshot_date, sku, "OnDemand", "USD", unit, price, "", "", f"{sku} {text}",
                 begin, end, location)
            )
    loc, sku, reserved = RESERVED
    if loc == location:
        rows["price_fact"].append(
            (snapshot_date, sku, "Reserved", "USD", "Quantity", reserved[week_index], "1yr",
             "All Upfront", f"{sku} reserved upfront", "0", "Inf", location)
        )
    return rows


SCHEMAS = {
    "service_dim": "snapshot_date DATE, service_code VARCHAR, service_name VARCHAR, "
    "offer_code VARCHAR, publication_date VARCHAR, region VARCHAR",
    "product_dim": "snapshot_date DATE, sku VARCHAR, service_code VARCHAR, region_code VARCHAR, "
    "product_family VARCHAR, attributes_json VARCHAR, region VARCHAR",
    "product_attribute": "snapshot_date DATE, sku VARCHAR, service_code VARCHAR, "
    "attribute_name VARCHAR, attribute_value VARCHAR, region VARCHAR",
    "region_dim": "snapshot_date DATE, region_code VARCHAR, location VARCHAR, "
    "location_type VARCHAR, region VARCHAR",
    "price_fact": "snapshot_date DATE, sku VARCHAR, term VARCHAR, currency VARCHAR, unit VARCHAR, "
    "price DOUBLE, lease_contract_length VARCHAR, purchase_option VARCHAR, description VARCHAR, "
    "begin_range VARCHAR, end_range VARCHAR, region VARCHAR",
}


def _snapshot(con, snapshot_date: str, week_index: int, revision: int) -> dict:
    run_id = run_id_for(snapshot_date, revision)
    regions = list(LOCATIONS)
    tables: dict[str, dict] = {}
    for table in TABLES:
        table_regions = {}
        total = 0
        for location in regions:
            key = (
                f"{PROVIDER}/parquet/{table}/snapshot_date={snapshot_date}/region={location}/"
                f"part-{run_id}.parquet"
            )
            rows = _rows(snapshot_date, week_index, revision, location)[table]
            count = _write(con, OUT / key, SCHEMAS[table], rows)
            data = (OUT / key).read_bytes()
            table_regions[location] = {
                "written_by_run": run_id,
                "row_count": count,
                "files": [{
                    "path": key,
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "row_count": count,
                }],
            }
            total += count
        tables[table] = {"schema_version": 1, "row_count": total, "regions": table_regions}
    stamp = f"{snapshot_date}T00:00:00Z"
    return {
        "manifest_version": "1.0",
        "provider": PROVIDER,
        "snapshot_date": snapshot_date,
        "run_id": run_id,
        "revision": revision,
        "previous_revision": revision - 1 if revision > 1 else None,
        "created_at": stamp,
        "origin": "pipeline",
        "status": "succeeded",
        "regions": {"requested": regions, "succeeded": regions, "failed": []},
        "run": {
            "trigger": "scheduled",
            "mode": "full",
            "host": "test-fixture",
            "started_at": stamp,
            "ended_at": stamp,
            "pipeline_version": {"git_sha": "fixture", "image_tag": "fixture"},
            "region_results": [
                {"region": r, "outcome": "succeeded", "attempts": 1} for r in regions
            ],
        },
        "raw": None,
        "tables": tables,
        "purged": None,
    }


def build() -> None:
    if OUT.exists():
        for child in OUT.iterdir():
            if child.name != "README.md":
                shutil.rmtree(child) if child.is_dir() else child.unlink()
    con = duckdb.connect(config={"threads": 1})
    latest = None
    for index, snapshot_date in enumerate(WEEKS):
        manifest_dir = OUT / PROVIDER / "manifests" / snapshot_date
        manifest_dir.mkdir(parents=True, exist_ok=True)
        revisions = (1, 2) if snapshot_date == REVISED else (1,)
        for revision in revisions:
            manifest = _snapshot(con, snapshot_date, index, revision)
            text = json.dumps(manifest, indent=2) + "\n"
            (manifest_dir / "revisions").mkdir(exist_ok=True)
            (manifest_dir / "revisions" / f"{revision:04d}.json").write_text(text)
            (manifest_dir / "manifest.json").write_text(text)
        latest = manifest
    (OUT / PROVIDER / "manifests" / "latest.json").write_text(json.dumps({
        "manifest_version": "1.0",
        "provider": PROVIDER,
        "snapshot_date": latest["snapshot_date"],
        "revision": latest["revision"],
        "run_id": latest["run_id"],
        "manifest_path": f"{PROVIDER}/manifests/{latest['snapshot_date']}/manifest.json",
        "updated_at": latest["created_at"],
    }, indent=2) + "\n")
    print(f"wrote {len(WEEKS)} weekly snapshots ({REVISED} with 2 revisions) to {OUT}")


if __name__ == "__main__":
    build()
