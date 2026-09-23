"""Build the small AWS pricing Parquet fixture used by the test suite in CI.

The real pricing dataset (~2.3 GB, produced by a separate upstream project) isn't in this repo,
so CI points `AWS_PRICING_PARQUET_DIR` at a subset of it instead: every table and region
partition of one snapshot date, but only the rows for the SKUs the tests reference (plus a
small sample per tested service so broad filters still match more than one row). Rows are
copied verbatim and in source order — nothing is fabricated, edited, or reordered (Constitution
Principle I; a few lookups take the first of several duplicate rows, so order matters).

Re-run whenever a test starts depending on a new SKU (add it to SEED_SKUS):

    uv run python scripts/build_test_pricing_fixture.py --source /path/to/DATA/pricing_aws/parquet \
        [--snapshot-date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import duckdb

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "pricing_parquet"
TABLES = ("service_dim", "product_dim", "product_attribute", "region_dim", "price_fact")

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
# Services whose broad filters (service_code/product_family/text) the tests exercise.
SAMPLED_SERVICES = ("AmazonEC2", "AmazonS3", "AWSDataTransfer")
SAMPLE_PER_SERVICE = 25
# fromRegionCode the region-code filter tests search for.
SAMPLED_FROM_REGION_CODE = "ap-southeast-2-per-1"


def _latest_common_snapshot(source: Path) -> str:
    common: set[str] | None = None
    for table in TABLES:
        dates = {
            p.name.removeprefix("snapshot_date=")
            for p in (source / table).iterdir()
            if p.name.startswith("snapshot_date=")
        }
        common = dates if common is None else common & dates
    if not common:
        raise SystemExit("no snapshot_date common to all pricing tables")
    return max(common)


def _partition(root: Path, table: str, snapshot_date: str, region: str) -> Path:
    return root / table / f"snapshot_date={snapshot_date}" / f"region={region}" / "part-0.parquet"


def _copy(con: duckdb.DuckDBPyConnection, query: str, params: list, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({query}) TO '{dest}' (FORMAT parquet, COMPRESSION zstd)", params)
    return con.execute("SELECT count(*) FROM read_parquet(?)", [str(dest)]).fetchone()[0]


def build(source: Path, out: Path, snapshot_date: str | None = None) -> None:
    snapshot_date = snapshot_date or _latest_common_snapshot(source)
    regions = sorted(
        p.name.removeprefix("region=")
        for p in (source / "product_dim" / f"snapshot_date={snapshot_date}").iterdir()
        if p.name.startswith("region=")
    )
    if out.exists():
        shutil.rmtree(out)
    con = duckdb.connect()
    seed_pattern = "|".join(SEED_SKUS)

    for region in regions:
        src = {t: str(_partition(source, t, snapshot_date, region)) for t in TABLES}
        dst = {t: _partition(out, t, snapshot_date, region) for t in TABLES}

        # Tiny dimension tables: copy whole.
        for table in ("service_dim", "region_dim"):
            _copy(con, "SELECT * FROM read_parquet(?)", [src[table]], dst[table])

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
        skus = [r[0] for r in con.execute(
            "SELECT DISTINCT sku FROM read_parquet(?)", [str(dst["product_dim"])]
        ).fetchall()]

        for table in ("product_attribute", "price_fact"):
            _copy(
                con,
                "SELECT * FROM read_parquet(?) WHERE sku IN (SELECT unnest(?::VARCHAR[]))",
                [src[table], skus],
                dst[table],
            )
        print(f"{region}: {n} product rows, {len(skus)} skus")

    print(f"wrote snapshot {snapshot_date} to {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, required=True, help="full pricing parquet dir")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--snapshot-date",
        help="YYYY-MM-DD to copy (default: latest common to all tables); pin a finished "
        "snapshot if the upstream pipeline may still be writing today's",
    )
    args = parser.parse_args()
    build(args.source, args.out, args.snapshot_date)


if __name__ == "__main__":
    main()
