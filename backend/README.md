# Cloud Pricing Backend

FastAPI backend for AWS Architecture Assembly & Pricing. See
`specs/001-assemble-price-aws-architecture/` (plan.md, data-model.md, contracts/api.md) for the
full design, and `quickstart.md` for a scripted end-to-end validation of the API.

## Setup

```bash
brew install postgresql@18     # if not already installed
brew services start postgresql@18
createdb cloud_pricing_dev
createdb cloud_pricing_test     # used by the test suite

uv sync --extra dev
source .venv/bin/activate
alembic upgrade head
```

## Configuration

Environment variables (see `src/config.py`):

- `DATABASE_URL` — defaults to `postgresql+psycopg://localhost/cloud_pricing_dev`
- `PRICING_DATA_URI` — **required**: the pricing pipeline's storage root, a local folder
  (`file:///…/DATA/pipeline`) or `s3://bucket[/prefix]`. Snapshots are found only through the
  pipeline's manifests; the old `snapshot_date=`/`_SUCCESS` layout and the old
  `AWS_PRICING_PARQUET_DIR` setting are no longer supported (see
  [`docs/configuration.md`](../docs/configuration.md#pricing-data) for converting old data).
- `AWS_PRICING_REGION` — defaults to `us-east-1`

The full list of settings (including the pricing-snapshot check interval, the
`ACTIVE_SNAPSHOT_DATE` override, CORS origins, catalog page sizes, password hashing, and log level),
with defaults and environment variable names, is in
[`docs/configuration.md`](../docs/configuration.md). A commented template is in
[`.env.example`](.env.example).

## Run

```bash
DATABASE_URL="postgresql+psycopg://localhost/cloud_pricing_dev" uvicorn src.main:app --reload --port 8000
```

Then visit `http://localhost:8000/openapi.json` for the live OpenAPI schema (the frontend's
types are generated from this — see `frontend/README.md`).

## Test

```bash
# Requires cloud_pricing_test to exist and be migrated (alembic upgrade head against it too).
TEST_DATABASE_URL="postgresql+psycopg://localhost/cloud_pricing_test" pytest
```

The tests run against a real Postgres database and real AWS pricing Parquet data (no mocks for
either — per the constitution, pricing data is only ever read from its real source). Every test
module needs Postgres, because `tests/conftest.py` cleans the tables before each test.

`tests/fixtures/pricing_parquet/` is a small (~300 KB) verbatim subset of the upstream data, in
the pipeline's storage layout (`aws/parquet/…`, `aws/manifests/<date>/manifest.json`,
`aws/manifests/latest.json`). It holds one snapshot, with every table and region, but only the
SKUs the tests reference. The tests use it by default (`tests/conftest.py` sets
`PRICING_DATA_URI` to it unless you set it), so they need no network.

Rebuild it after a test starts depending on a new SKU (add the SKU to `SEED_SKUS` first), from a
pipeline storage root or from the legacy folder tree:

```bash
uv run python scripts/build_test_pricing_fixture.py --source-uri file:///path/to/DATA/pipeline
uv run python scripts/build_test_pricing_fixture.py --source /path/to/DATA/pricing_aws/parquet
```

`tests/fixtures/contracts/` holds the pipeline's contracts, copied verbatim (see `SOURCE.md`);
`tests/contract/test_manifest_schema_compat.py` checks the app still reads them.

Backup and restore tests (`tests/integration/test_backup_roundtrip.py`,
`test_db_init_restore.py`) need `pg_dump` and `pg_restore` 18 on `PATH` and skip otherwise.

## Standard architectures

Migration `0005_standard_architectures` seeds four public, Admin-owned architectures from
`src/db/seed/standard_architectures.json`. An Alembic revision runs once per database, so each
architecture is created once. If the Admin deletes or renames one, it isn't recreated. The
migration needs no pricing data at run time, because the seed already holds resolved
`service_code`/`sku` references.

The seed and its report (`src/db/seed/standard_architectures_report.md`) are generated. Don't
edit them by hand. To change what gets seeded, edit the rules in
`scripts/standard_architectures/match_rules.py` (one rule per usage figure in
`docs/common_aws_architectures.md`) and re-run the resolver against the real pricing data:

```bash
uv run python scripts/resolve_standard_architectures.py [--data-uri file:///path/to/DATA/pipeline]
```

It reads the snapshot `latest.json` names; pin another with `ACTIVE_SNAPSHOT_DATE=YYYY-MM-DD`.

Check the report for figures left out and for SKUs flagged as tiered. Then rebuild the test
fixture against the same snapshot, because it reads the seeded SKUs from the seed file:

```bash
uv run python scripts/build_test_pricing_fixture.py --source-uri file:///path/to/DATA/pipeline \
    --snapshot-date YYYY-MM-DD
```

A database that has already run `0005` doesn't pick up a regenerated seed. To bring back a
standard architecture the Admin deleted, import `src/db/seed/standard_architectures.json` on the
Admin row of the Admin tab. It uses the same file format as Export/Import.

## Lint

```bash
ruff check src/
```
