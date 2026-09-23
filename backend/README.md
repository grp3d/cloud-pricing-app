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
- `AWS_PRICING_PARQUET_DIR` — base directory containing the AWS pricing Parquet tables
  (`service_dim/`, `product_dim/`, `product_attribute/`, `region_dim/`, `price_fact/`),
  produced by a separate upstream project. Read-only.
- `AWS_PRICING_REGION` — defaults to `us-east-1`

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

`tests/fixtures/pricing_parquet/` is a small (~300 KB) verbatim subset of the upstream data. It
holds one snapshot, with every table and region partition, but only the SKUs the tests reference.
CI uses it, and you can too:

```bash
AWS_PRICING_PARQUET_DIR="$PWD/tests/fixtures/pricing_parquet" \
TEST_DATABASE_URL="postgresql+psycopg://localhost/cloud_pricing_test" pytest
```

Rebuild it after a test starts depending on a new SKU (add the SKU to `SEED_SKUS` first):

```bash
uv run python scripts/build_test_pricing_fixture.py --source /path/to/DATA/pricing_aws/parquet
```

## Lint

```bash
ruff check src/
```
