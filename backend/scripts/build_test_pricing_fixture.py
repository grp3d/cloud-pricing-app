"""Build the small AWS pricing Parquet fixture used by the test suite in CI.

The real pricing dataset (~2.3 GB, produced by a separate upstream project) isn't in this repo,
so CI points `PRICING_DATA_URI` at a subset of it instead: every table and region of one
snapshot date, but only the rows for the SKUs the tests reference (plus a small sample per
tested service so broad filters still match more than one row). Rows are copied verbatim and in
source order — nothing is fabricated, edited, or reordered (Constitution Principle I; a few
lookups take the first of several duplicate rows, so order matters).

018-app-cloud-deployment (FR-004, research.md R15): the fixture is written in the pipeline's
storage layout (`storage-layout.md`, vendored in `tests/fixtures/contracts/`), exactly as the app
reads it:

    <out>/aws/parquet/<table>/snapshot_date=<D>/region=<R>/part-<run_id>.parquet
    <out>/aws/manifests/<D>/manifest.json     # status "succeeded", origin "backfill"
    <out>/aws/manifests/latest.json

with real `bytes`, `sha256` and `row_count` for every file. The source can be the legacy local
tree (`snapshot_date=` folders) or a pipeline storage root (found through its manifest).

Re-run whenever a test starts depending on a new SKU (add it to SEED_SKUS):

    uv run python scripts/build_test_pricing_fixture.py \
        --source /path/to/DATA/pricing_aws/parquet [--snapshot-date YYYY-MM-DD]
    uv run python scripts/build_test_pricing_fixture.py \
        --source-uri file:///path/to/DATA/pipeline [--snapshot-date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

import duckdb

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "pricing_parquet"
STANDARD_ARCHITECTURES_SEED = (
    Path(__file__).resolve().parent.parent / "src" / "db" / "seed" / "standard_architectures.json"
)
TABLES = ("service_dim", "product_dim", "product_attribute", "region_dim", "price_fact")
PROVIDER = "aws"
# A fixed, contract-valid run id (`<yyyymmddThhmmssZ>-<6 hex>`), so file names don't churn.
RUN_ID = "20260924T000000Z-f1a7e0"

# Every SKU a test names directly.
SEED_SKUS = (
    "NN4EGUUQRWVYP98C",  # t3.medium Linux on-demand, region_code us-east-1
    "2QF2GD6XUCJHFMKF",  # NAT Gateway usage-type
    "QZ9R39S2Y8MCC9Y8",  # reserved-term SKU (duration pricing)
    "2AB37QDFJZBGQ5YP",  # m5.16xlarge with duplicate price rows
    "2THCJ54S3VW8G6VS",  # reserved-term SKU (bug report)
    "47NTBKB4KMUU98P8",  # t3.medium Linux on-demand, region_code eu-west-1
    "28EK9CZBYC9JU7KW",  # AWSDataTransfer us-east-1 -> us-west-2-pdx-1
)


def _standard_architecture_skus() -> tuple[str, ...]:
    """Every SKU the checked-in standard-architecture seed references
    (014-architecture-templates-import-export) — read from the seed itself so a re-resolved
    seed can never drift from what the fixture covers. Rebuild the fixture after re-running
    `scripts/resolve_standard_architectures.py`, against the same snapshot date."""
    seed = json.loads(STANDARD_ARCHITECTURES_SEED.read_text())
    return tuple(
        sorted(
            {
                selection["sku"]
                for architecture in seed["architectures"]
                for collection in architecture["collections"]
                for selection in collection["sku_selections"]
            }
        )
    )


SEED_SKUS = SEED_SKUS + _standard_architecture_skus()
# Services whose broad filters (service_code/product_family/text) the tests exercise.
SAMPLED_SERVICES = ("AmazonEC2", "AmazonS3", "AWSDataTransfer")
SAMPLE_PER_SERVICE = 25
# fromRegionCode the region-code filter tests search for.
SAMPLED_FROM_REGION_CODE = "ap-southeast-2-per-1"


# --- Sources: where the full data is read from -------------------------------------------------


class LegacySource:
    """The old local tree: `<root>/<table>/snapshot_date=<D>/region=<R>/*.parquet`."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def default_date(self) -> str:
        common: set[str] | None = None
        for table in TABLES:
            dates = {
                p.name.removeprefix("snapshot_date=")
                for p in (self.root / table).iterdir()
                if p.name.startswith("snapshot_date=")
            }
            common = dates if common is None else common & dates
        if not common:
            raise SystemExit("no snapshot_date common to all pricing tables")
        return max(common)

    def regions(self, snapshot_date: str) -> list[str]:
        date_dir = self.root / "product_dim" / f"snapshot_date={snapshot_date}"
        return sorted(
            p.name.removeprefix("region=") for p in date_dir.iterdir()
            if p.name.startswith("region=")
        )

    def files(self, table: str, snapshot_date: str, region: str) -> list[str]:
        region_dir = self.root / table / f"snapshot_date={snapshot_date}" / f"region={region}"
        return sorted(str(p) for p in region_dir.glob("*.parquet"))


class PipelineSource:
    """A pipeline storage root (new layout), read only through its manifests."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._manifests: dict[str, dict] = {}

    def default_date(self) -> str:
        latest = json.loads((self.root / PROVIDER / "manifests" / "latest.json").read_text())
        return latest["snapshot_date"]

    def _manifest(self, snapshot_date: str) -> dict:
        if snapshot_date not in self._manifests:
            path = self.root / PROVIDER / "manifests" / snapshot_date / "manifest.json"
            manifest = json.loads(path.read_text())
            if manifest["status"] != "succeeded":
                raise SystemExit(f"{path}: status is {manifest['status']}, not succeeded")
            self._manifests[snapshot_date] = manifest
        return self._manifests[snapshot_date]

    def regions(self, snapshot_date: str) -> list[str]:
        return sorted(self._manifest(snapshot_date)["tables"]["product_dim"]["regions"])

    def files(self, table: str, snapshot_date: str, region: str) -> list[str]:
        entry = self._manifest(snapshot_date)["tables"][table]["regions"][region]
        return [str(self.root / f["path"]) for f in entry["files"]]


# --- Writing the new layout ---------------------------------------------------------------------


def _data_key(table: str, snapshot_date: str, region: str) -> str:
    return (
        f"{PROVIDER}/parquet/{table}/snapshot_date={snapshot_date}/region={region}/"
        f"part-{RUN_ID}.parquet"
    )


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


def _manifest(snapshot_date: str, regions: list[str], tables: dict) -> dict:
    stamp = f"{snapshot_date}T00:00:00Z"
    return {
        "manifest_version": "1.0",
        "provider": PROVIDER,
        "snapshot_date": snapshot_date,
        "run_id": RUN_ID,
        "revision": 1,
        "previous_revision": None,
        "created_at": stamp,
        "origin": "backfill",
        "status": "succeeded",
        "regions": {"requested": regions, "succeeded": regions, "failed": []},
        "run": {
            "trigger": "backfill",
            "mode": "backfill",
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


def build(source: LegacySource | PipelineSource, out: Path, snapshot_date: str | None) -> None:
    snapshot_date = snapshot_date or source.default_date()
    regions = source.regions(snapshot_date)
    if out.exists():
        shutil.rmtree(out)
    con = duckdb.connect()
    seed_pattern = "|".join(SEED_SKUS)
    tables: dict[str, dict] = {
        t: {"schema_version": 1, "row_count": 0, "regions": {}} for t in TABLES
    }

    def record(table: str, region: str, row_count: int) -> None:
        key = _data_key(table, snapshot_date, region)
        tables[table]["regions"][region] = {
            "written_by_run": RUN_ID,
            "row_count": row_count,
            "files": [_file_entry(out, key, row_count)],
        }
        tables[table]["row_count"] += row_count

    for region in regions:
        src = {t: source.files(t, snapshot_date, region) for t in TABLES}
        dst = {t: out / _data_key(t, snapshot_date, region) for t in TABLES}

        # Tiny dimension tables: copy whole.
        for table in ("service_dim", "region_dim"):
            n = _copy(con, "SELECT * FROM read_parquet(?)", [src[table]], dst[table])
            record(table, region, n)

        # product_dim: seed SKUs, rows whose attributes reference a seed SKU (e.g. Capacity
        # Reservation variants naming it as `instancesku`), a per-service sample, and a few
        # AWSDataTransfer rows from the sampled fromRegionCode.
        sampled = ", ".join(f"'{s}'" for s in SAMPLED_SERVICES)
        product_query = f"""
            WITH src AS (SELECT * FROM read_parquet(?)),
            picked AS (
                SELECT sku FROM src
                WHERE sku IN (SELECT unnest(?::VARCHAR[]))
                   OR regexp_matches(attributes_json, ?)
                UNION
                SELECT sku FROM (
                    SELECT sku, row_number() OVER (PARTITION BY service_code ORDER BY sku) AS n
                    FROM src WHERE service_code IN ({sampled})
                ) WHERE n <= {SAMPLE_PER_SERVICE}
                UNION
                SELECT sku FROM (
                    SELECT sku FROM src
                    WHERE service_code = 'AWSDataTransfer'
                      AND json_extract_string(attributes_json, '$.fromRegionCode') = ?
                    ORDER BY sku LIMIT 10
                )
            )
            SELECT * FROM src WHERE sku IN (SELECT sku FROM picked)
        """
        n = _copy(
            con,
            product_query,
            [src["product_dim"], list(SEED_SKUS), seed_pattern, SAMPLED_FROM_REGION_CODE],
            dst["product_dim"],
        )
        record("product_dim", region, n)
        skus = [r[0] for r in con.execute(
            "SELECT DISTINCT sku FROM read_parquet(?)", [str(dst["product_dim"])]
        ).fetchall()]

        for table in ("product_attribute", "price_fact"):
            rows = _copy(
                con,
                "SELECT * FROM read_parquet(?) WHERE sku IN (SELECT unnest(?::VARCHAR[]))",
                [src[table], skus],
                dst[table],
            )
            record(table, region, rows)
        print(f"{region}: {n} product rows, {len(skus)} skus")

    manifest_key = f"{PROVIDER}/manifests/{snapshot_date}/manifest.json"
    manifest = _manifest(snapshot_date, regions, tables)
    (out / manifest_key).parent.mkdir(parents=True, exist_ok=True)
    (out / manifest_key).write_text(json.dumps(manifest, indent=2) + "\n")
    latest = {
        "manifest_version": "1.0",
        "provider": PROVIDER,
        "snapshot_date": snapshot_date,
        "revision": 1,
        "run_id": RUN_ID,
        "manifest_path": manifest_key,
        "updated_at": f"{snapshot_date}T00:00:00Z",
    }
    (out / PROVIDER / "manifests" / "latest.json").write_text(json.dumps(latest, indent=2) + "\n")
    print(f"wrote snapshot {snapshot_date} to {out}")


def _source_from_uri(uri: str) -> PipelineSource:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise SystemExit("--source-uri must be a file:// pipeline storage root")
    return PipelineSource(Path(parsed.path))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source", type=Path, help="legacy full pricing parquet dir")
    group.add_argument("--source-uri", help="file:// pipeline storage root (new layout)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--snapshot-date",
        help="YYYY-MM-DD to copy (default: latest common date, or the source's latest.json)",
    )
    args = parser.parse_args()
    source = LegacySource(args.source) if args.source else _source_from_uri(args.source_uri)
    build(source, args.out, args.snapshot_date)


if __name__ == "__main__":
    main()
