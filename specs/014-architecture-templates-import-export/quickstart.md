# Quickstart: Validating Standard Architectures and Admin Import/Export

This guide proves the feature works end-to-end. The contracts are in [contracts/](contracts/), and the entities and validation rules are in [data-model.md](data-model.md).

## Prerequisites

- Local Postgres with `cloud_pricing_dev` and `cloud_pricing_test`, as for every earlier feature.
- The real pricing dataset at `AWS_PRICING_PARQUET_DIR`. It is needed only for step 1 and for pricing the standard architectures in the UI.
- The backend (`cd backend && uv run uvicorn src.main:app --reload`) and frontend (`cd frontend && npm run dev`) running.

## 1. Regenerate the resolved seed (developer step, only when the source JSON or match rules change)

```bash
cd backend
uv run python scripts/resolve_standard_architectures.py \
  --source ../docs/common_aws_architectures.md \
  --parquet "$AWS_PRICING_PARQUET_DIR"
```

**Expected**:
- `src/db/seed/standard_architectures.json` and `src/db/seed/standard_architectures_report.md` are rewritten. Running the script twice gives a byte-identical file.
- The report lists four architectures and one line per usage figure, each showing a matched SKU and unit or the reason it was left out.
- At minimum the report shows these as left out: App Mesh (no pricing records) and the RDS gp3 IOPS figure (included in the baseline).
- The script exits non-zero if any chosen SKU's billing unit isn't recognized by `pricing_data/duration.py` (research §6).

## 2. Seed the standard architectures

```bash
cd backend && uv run alembic upgrade head
```

**Expected**: Log in as `Admin` / `admin123`. Column 1 lists all four standard architectures (US1 AS1). Run `alembic upgrade head` again: nothing changes and no duplicates appear (US1 AS7).

## 3. Check a standard architecture's structure and pricing

1. Open "Active-Standby Multi-Region Web Application".
   - **Expected**: exactly two VPCs, `VPC (us-east-1)` and `VPC (us-west-2)`, and no application components or connectors.
   - Route 53 and CloudFront sit in the us-east-1 VPC (FR-006).
   - The primary S3 bucket appears as separate storage, PUT and GET entries (US1 AS8).
2. Price it for 1 month.
   - **Expected**: every entry is priced. The unpriceable list is empty, apart from anything the report says has no match (SC-003).
3. Log in as another named user, open **Import** in column 1, and copy "Serverless Microservices Back-End".
   - **Expected**: it appears under the Admin group (US1 AS2).
   - The copy has one `VPC (eu-west-1)` containing CloudFront, Cognito, API Gateway, Lambda (requests and GB-seconds), DynamoDB, SQS and SNS entries (US1 AS4).

## 4. Export

1. As Admin, open the Admin tab.
   - **Expected**: the columns read "Users · Active · Password · Import Architectures from Disk · Export Architectures to Disk · Purge". The two new headers wrap onto multiple lines, and the table doesn't scroll horizontally (FR-011, SC-008).
2. A user with no architectures has a disabled **Export** button (FR-012).
3. Click **Export** on the Admin row.
   - **Expected**: the browser downloads `Admin_<YYYYMMDDTHHMMSS>.json` containing all four standard architectures in the format of [contracts/export-format.md](contracts/export-format.md). The file has no ids, no `is_public` and no prices (FR-016).

## 5. Import: round trip and partial failure

1. Create user `qa1`. Click **Import** on its row and choose the file from step 4.
   - **Expected**: the popup lists four ✓ rows. `qa1` now owns four private architectures identical in structure and pricing inputs to the Admin's (SC-004, FR-023).
2. Import the same file into `qa1` again.
   - **Expected**: four ✗ rows, each "Architecture name already exists", and nothing added (US3 AS3).
3. Edit a copy of the file:
   - Rename one entry to something new.
   - Change another entry's SKU to `ZZZZZZZZZZZZZZZZ` and also rename it.
   - Leave the other two unchanged.

   Import it into `qa1`.
   - **Expected**: one ✓, one ✗ "Service not found in pricing data: … ZZZZZZZZZZZZZZZZ …" and two ✗ "Architecture name already exists".
   - Only the renamed valid architecture is added, and nothing is left from the failed one (US3 AS4–AS6, SC-006).
4. Import a `.txt` file, a JSON array, and the old baseline JSON from `docs/functionality_2026-09-25.md`.
   - **Expected**: each shows "Import failed" and nothing changes (FR-019).
5. Open the file picker and cancel.
   - **Expected**: nothing happens (Edge Cases).

## 6. Access control

As a non-admin user, and as a guest, check the following.

**Expected**:
- The Admin tab isn't shown.
- Direct `GET …/architectures/export` and `POST …/architectures/import` calls return `403` or `401` (FR-025, SC-007).
- The column-1 **Import** from feature 012 still works unchanged (FR-024).

## 7. Automated suites

```bash
cd backend && uv run pytest -v
cd frontend && npm test && npm run build && npm run check-api-types
```

**Expected**: everything passes. CI runs the same commands against the Parquet fixture. The fixture is rebuilt to include the SKUs the new tests reference (`scripts/build_test_pricing_fixture.py` `SEED_SKUS`).

## Validation notes (2026-09-25 browser walkthrough)

These steps were run in Chrome against the dev database (`alembic` head `7c2e9d41b8a3`) and pricing snapshot `2026-09-24`.

- **Step 3 ✅** demo1, a non-admin user, sees all four standard architectures under **Admin** in the Import list. The copy "My Serverless Microservices Back-End" has one `VPC (eu-west-1)`, keeps the seeded service order, and prices at $136.32/month with 0 unpriceable entries. DynamoDB storage and SNS show $0.00 because of the known tiered-pricing first-row behavior (research §7.3, report "tiered" column).
- **Step 4 ✅**
  - The columns read Users · Active · Password · Import Architectures from Disk · Export Architectures to Disk · Purge, with both new headers wrapped onto 2 lines.
  - The table is 672px wide and the document has no horizontal scroll at a 1392px window.
  - Export is disabled for users with 0 architectures (demo2, and qa1 before import).
  - Export on Admin saved `Admin_20260925T141636.json`: format v1 with all 5 Admin architectures, and no `id`/`user_id`/`is_public`/`price`/`deleted_at` keys.
  - Deviation: this Chrome profile asks where to save each file, so the download needed a manual Save.
- **Step 5 ✅** Each file was imported into the new user `qa1`:

  | File | Result |
  |---|---|
  | The export | 5 ✓ |
  | The same export again | 5 ✗ "Architecture name already exists" |
  | Mixed file | 1 ✓, 1 ✗ "Service not found in pricing data: AmazonRoute53 / ZZZZZZZZZZZZZZZZ (us-east-1)", 2 ✗ name exists |
  | Non-JSON file | "Import failed: the file is not valid JSON." |
  | Old baseline JSON | "Import failed: the file is not an architecture export." |
  | JSON array | "Import failed: the file is not in the expected format." |

  - `qa1` ends with 6 private architectures, and no rows remain from the failed entry.
  - Re-exporting `qa1` gives architectures identical to the original export (SC-004).
- **Step 5, cancelled picker (not exercised in the browser):** a native file picker can't be driven by the automation, so the code path (no file → no request, input reset) was reviewed but not clicked through.
- **Step 6 ✅** demo1 has no Admin tab, and gets 403 on both `…/architectures/export` and `…/architectures/import`.
- **Console:** one React dev-mode warning, "Function components cannot be given refs", from the pre-existing `components/ui/dialog.tsx` `DialogOverlay`. Every dialog raises it, not only the new one.
