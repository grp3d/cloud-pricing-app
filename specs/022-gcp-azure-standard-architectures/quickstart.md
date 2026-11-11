# Quickstart: validating the GCP and Azure standard architectures

## Prerequisites

- Local development is set up as in [docs/development.md](../../docs/development.md): Postgres
  running, and `backend/.env` with `PRICING_DATA_URI=file:///…/_DATA-PIPELINE`.
- The local GCP and Azure pricing data includes the regions the designs use (research R1). The
  current local snapshots (2026-11-02) are US-only. Add the European regions, from the data
  pipeline repo:

  ```bash
  cd ../cloud-pricing-data-retrieval
  PIPELINE_STORAGE_URI=file:///…/_DATA-PIPELINE PIPELINE_PROVIDER=gcp \
      python -m src.pipeline run --regions europe-west1
  PIPELINE_STORAGE_URI=file:///…/_DATA-PIPELINE PIPELINE_PROVIDER=azure \
      python -m src.pipeline run --regions westeurope
  ```

  A subset run publishes a new revision that keeps the other locations
  (pipeline `docs/cli.md`).

## 1. Generate (only when rules or data change)

```bash
cd backend
uv run python scripts/resolve_standard_architectures.py --provider gcp
uv run python scripts/resolve_standard_architectures.py --provider azure
uv run python scripts/resolve_standard_architectures.py            # AWS: expect no diff
git diff --stat src/db/seed/
```

**Expected**:
- New `standard_architectures_{gcp,azure}.json` and `_report.md` files.
- No change to `standard_architectures.json` or `standard_architectures_report.md`.
- Running each command again gives no diff (SC-005).

Read both reports. Every AWS component appears for each provider, either matched or left out
with a reason (SC-004), and sized rows show "original → chosen".

## 2. Rebuild the test data set

```bash
uv run python scripts/build_provider_fixtures.py --source-uri file:///…/_DATA-PIPELINE
```

**Expected**: `tests/fixtures/pricing_parquet/{gcp,azure}/` gain the seeded SKUs and the new
locations. The AWS fixture is untouched.

## 3. Tests

```bash
uv run pytest tests/unit -k standard_architect
uv run pytest tests/integration -k "standard_architecture or db_init_restore"
```

To run the restore tests, Postgres client tools must be on PATH:

```bash
PATH=/opt/homebrew/opt/postgresql@18/bin:$PATH uv run pytest tests/integration/test_db_init_restore.py
```

**Expected**: all pass. They cover seed validation, every one of the eight priced with nothing
unpriceable, migration 0009's skip rules, and the restore from a pre-0009 backup adding exactly
eight.

## 4. In the app

```bash
cd backend && uv run alembic upgrade head      # local DB at 0008 -> 0009
```

1. Log in as any user. Open the header architecture menu → Import. The GCP and Azure groups
   each list the four Admin architectures.
2. Log in as `Admin`. The menu's GCP and Azure groups each show the four (SC-001).
3. Open each GCP and Azure one and press Calculate. The total is non-zero, there are no
   unpriceable rows, and services show provider icons (SC-002).
4. Open the GCP web app's Compute Engine service. Its vCPU and memory fields are 4 and 16.
   Price Change works on it.
5. Calculate the AWS, GCP and Azure "Serverless Microservices Back-End" at 1 month and compare
   the totals (Story 4).

## 5. Deployed environment

After the release tag, run `deploy/app up`. The `db-init` log shows the migration to
`<0009 revision>`. The site shows 4 standard architectures per provider. Running `up` again
after `down` (restoring the teardown backup) adds nothing more (SC-003).
