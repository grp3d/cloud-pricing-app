# Quickstart: Validate AWS Architecture Assembly & Pricing

This script proves User Story 1 (the P1 core loop) works end-to-end against the real API,
before the frontend UI exists. It doubles as the smoke test to re-run after implementation.

## Prerequisites

- Python 3.12+ and `uv` installed; Node.js 20+ and `npm` installed.
- A running PostgreSQL instance, with `DATABASE_URL` set for the backend.
- Read access to the AWS pricing Parquet data at
  `/Users/ghubs/Development/repos/personal/cloud-pricing/DATA/pricing_aws/parquet` (or the path
  configured via the backend's pricing-data settings).
- A test user identity available to authenticate as (per FR-002; exact mechanism is an
  implementation detail — see `research.md`/`tasks.md`).

## Setup

```bash
# Backend
cd backend
uv sync
uv run alembic upgrade head        # applies the Postgres schema from data-model.md
uv run uvicorn src.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run generate-api-types          # openapi-typescript against http://localhost:8000/openapi.json
npm run dev
```

## Validate: end-to-end assemble-and-price flow (User Story 1)

Run against the backend directly (`http://localhost:8000/api/v1`), authenticated as the test
user. Replace `$TOKEN` with whatever the chosen auth mechanism issues.

```bash
BASE=http://localhost:8000/api/v1
AUTH=(-H "Authorization: Bearer $TOKEN")

# 1. Confirm AWS is the only active provider (FR-003)
curl -s "${AUTH[@]}" "$BASE/providers" | jq
# Expect: aws.active == true, gcp.active == false, azure.active == false

# 2. Create an Architecture (FR-001, FR-002)
ARCH_ID=$(curl -s "${AUTH[@]}" -X POST "$BASE/architectures" \
  -H 'Content-Type: application/json' \
  -d '{"name": "Quickstart Web App", "provider": "aws"}' | jq -r .id)

# 3. Add a Collection (FR-004)
COLL_ID=$(curl -s "${AUTH[@]}" -X POST "$BASE/architectures/$ARCH_ID/collections" \
  -H 'Content-Type: application/json' \
  -d '{"type": "application_component", "name": "Web tier"}' | jq -r .id)

# 4. Search the catalog for an EC2 SKU (FR-005)
curl -s "${AUTH[@]}" "$BASE/catalog/skus?service_code=AmazonEC2&product_family=Compute+Instance&q=t3.medium" | jq
# Pick one `sku` from the results, e.g. SKU_ID=...

# 5. Add that SKU to the Collection with pricing inputs (FR-006, FR-007)
curl -s "${AUTH[@]}" -X POST "$BASE/collections/$COLL_ID/sku-selections" \
  -H 'Content-Type: application/json' \
  -d "{\"service_code\": \"AmazonEC2\", \"sku\": \"$SKU_ID\", \"pricing_term\": \"on_demand\", \"purchase_option\": \"not_applicable\", \"usage_quantity\": 730}"

# 6. Calculate the price (FR-010, FR-011, FR-012)
curl -s "${AUTH[@]}" -X POST "$BASE/architectures/$ARCH_ID/calculate" | jq
# Expect: total_price > 0, snapshot_date present, line_items[0].priceable == true
```

**Expected outcome**: step 6 returns a `total_price` traceable to a real `snapshot_date`
(SC-002), matching the P1 acceptance scenarios in `spec.md`.

## Validate: connectors add to the total (User Story 2)

```bash
COLL2_ID=$(curl -s "${AUTH[@]}" -X POST "$BASE/architectures/$ARCH_ID/collections" \
  -H 'Content-Type: application/json' \
  -d '{"type": "vpc", "name": "App VPC"}' | jq -r .id)

CONN_ID=$(curl -s "${AUTH[@]}" -X POST "$BASE/architectures/$ARCH_ID/connectors" \
  -H 'Content-Type: application/json' \
  -d "{\"from_collection_id\": \"$COLL_ID\", \"to_collection_id\": \"$COLL2_ID\"}" | jq -r .id)

# Attach a NAT Gateway SKU to the connector, then re-run step 6 above and confirm
# total_price increased by the connector's line item.
```

## Validate: soft delete (User Story 3)

```bash
curl -s -o /dev/null -w '%{http_code}\n' "${AUTH[@]}" -X DELETE "$BASE/architectures/$ARCH_ID"
# Expect: 204

curl -s "${AUTH[@]}" "$BASE/architectures?provider=aws" | jq 'map(select(.id == "'"$ARCH_ID"'"))'
# Expect: [] — deleted Architecture no longer listed, per SC-004
```

## Frontend smoke check

With both servers running, open the frontend dev server URL and repeat the same flow through
the UI: select AWS → create an Architecture → add a Collection → search and add a SKU → enter
pricing inputs → Calculate. Confirm the displayed total matches the API response from step 6.
