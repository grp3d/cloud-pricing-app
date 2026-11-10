# Quickstart: Validate 019-gcp-azure-providers-trends

**Purpose**: Steps to show the feature works end to end. The design details are in [data-model.md](./data-model.md) and [contracts/api.md](./contracts/api.md).

## Prerequisites

- The app runs locally as in the repo README: backend `uv run uvicorn src.main:app`, frontend `npm run dev`, and Postgres.
- `PRICING_DATA_URI` points at a pipeline root that has `aws/`, `azure/` and `gcp/`, each with a `succeeded` snapshot. To build one locally:
  - in `../cloud-pricing-data-retrieval`, run `PIPELINE_PROVIDER=azure … run --regions eastus` and `PIPELINE_PROVIDER=gcp … run --regions us-east1`, as in its 004 quickstart Part B;
  - add AWS as today.
- For Trends: at least **3 weekly snapshots** for one provider. The pipeline's `upload-history` or repeated runs with different dates can produce them.
- Migrations `0006` and `0007` are applied, with `uv run alembic upgrade head`.

## A. Automated checks

```bash
cd backend && uv run pytest                 # all unit, contract and integration tests
cd backend && uv run ruff check .
cd frontend && npm run check-api-types && npm run build && npm test
```

Expected: everything passes. Every pre-existing AWS test passes unchanged, apart from the tier tests updated on purpose (research R3, R8); that is the regression guard.

## B. GCP and Azure in the workspace (US1)

1. Open the workspace. **Expected**: the GCP and Azure buttons in column 1 are enabled. Hovering one shows its snapshot date.
2. Select **Azure** and create an architecture with a collection in `eastus`.
   1. Search with kind **VM** for `D4s v5`, add it as Linux, on-demand, 730 hours. **Expected**: the price equals the reference lookup row (pipeline 004 data-model, "Lookup example") for the snapshot shown.
   2. Add a **P10 LRS Disk** (Premium SSD Managed Disks) and **outbound data transfer** on a connector, 500 GB. **Expected**: the transfer line shows tiers, with the first 100 GB at the published first-tier rate ($0) and the remaining 400 GB at the next tier's rate.
3. Select **GCP**, region `us-east1`, and add an **n2-standard-4** machine with 4 vCPUs and 16 GiB. **Expected**: the line shows its core and RAM parts, totaling 4 × core rate + 16 × RAM rate.
4. In an **AWS** architecture, add internet data transfer out of 20 TB (20,480 GB) per month. **Expected**: 10,240 GB at the first tier's rate plus 10,240 GB at the second tier's rate, shown as two tier parts (FR-008).
5. In each provider, search for a global-only item (Azure support, GCP licensing). **Expected**: it is listed as "global".
6. Point the GCP data at a root whose newest manifest is `failed` and refresh. **Expected**: GCP is disabled with its reason, while AWS and Azure keep working (FR-002, SC-008).
7. Export the Azure architecture and import it under another user. **Expected**: it is identical, and its total is unchanged.

## C. Trends charts (US2)

1. Open **Trends**. **Expected**: the defaults are all providers, all regions and all categories, with one up/down pair per provider (spec FR-012). There is no metric picker.
2. Select AWS with two regions and Compute. **Expected**: one AWS pair. Hovering a point shows the week, the up and down counts and their % of compared, and the counts compared and excluded.
3. Pick a provider with one snapshot. **Expected**: "not enough history yet".
4. Empty `PRICING_HISTORY_DIR` and restart, then open Trends during the backfill. **Expected**: "building history (n of m weeks)" with the weeks built so far. Restart again after it finishes. **Expected**: no snapshot is fetched again.
5. Check one week by hand: count the SKUs that went up and down between the two snapshots with DuckDB (the quickstart query in `tests/fixtures/trends/README.md`). **Expected**: the counts match the chart exactly (SC-005).

## D. Biggest movers (US3)

1. On the right of the page, choose AWS, Compute, all regions and 52 weeks. **Expected**: up to 3 increases and 3 decreases, each with start and end prices, unit and % change, or "No price changes in this period".
2. Check one entry against the two snapshots it names (SC-004a).

## E. Preferences (US4)

1. Change the Trends selections and a column width in browser A.
2. Sign in as the same user in browser B. **Expected**: the same selections and width (SC-006).
3. Press **Reset** on the charts section. **Expected**: only the charts section returns to the defaults, and that is still the case after a reload.
4. With browser-only settings from the previous release present, load the new release once. **Expected**: the values are kept, and `GET /me/preferences` shows `migrated_from_browser: true`.
5. Stop the backend briefly and resize a column. **Expected**: no blocking error; the change is saved after the backend returns.

## F. Diagram arrows (US5)

1. Set a connector to **one-way**, then **two-way**, then reverse it. **Expected**: the markers update, and the total is unchanged (SC-007).
2. Make it **one-to-many** and add a third box. **Expected**: one trunk branching to two boxes. Calculate: any data transfer appears once (FR-027a).
3. Delete one branch box. **Expected**: the connector is back to an ordinary one-way connector.
4. Reload, then export and import. **Expected**: the styles and branches are kept.
