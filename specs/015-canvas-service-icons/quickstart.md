# Quickstart: Validating Canvas Service Icons & Per-Architecture Pricing Results

This guide proves the feature works end-to-end. The contracts are in [contracts/](contracts/), and
the data shapes and state rules are in [data-model.md](data-model.md).

## Prerequisites

- Local Postgres with `cloud_pricing_dev` and `cloud_pricing_test`, as for every earlier feature.
- The real pricing dataset at `AWS_PRICING_PARQUET_DIR`, with the standard architectures seeded
  (014).
- For step 1 only: the AWS icon package at
  `../images-web/aws_architecture_icons` (release `07312026`).
- The backend (`cd backend && uv run uvicorn src.main:app --reload`) and frontend
  (`cd frontend && npm run dev`) running.

## 1. Regenerate the icon map (developer step, only when the icon package or pricing data changes)

```bash
cd backend
uv run python scripts/generate_aws_service_icon_map.py \
  --icons ../../images-web/aws_architecture_icons \
  --parquet "$AWS_PRICING_PARQUET_DIR"
```

**Expected**:
- `frontend/src/lib/awsServiceIcons.generated.ts` and `frontend/src/assets/aws-icons/*.svg` are
  rewritten. Running the script twice gives byte-identical output.
- The printed report lists matched, overridden and fallback service codes. At least 90% are
  non-fallback (SC-002), and every service code used by the seeded standard architectures is
  non-fallback, including `AWSDataTransfer` (Data Stream icon).

## 2. Automated checks

```bash
cd backend && uv run pytest                       # includes product_family contract/unit tests
cd frontend && npm run check-api-types && npm run lint && npm test && npm run build
```

**Expected**: all tests pass, `schema.d.ts` has `product_family` and no drift, and the build
succeeds.

## 3. Canvas icons (US1)

1. Open "Serverless Microservices Back-End".
   - **Expected**: the VPC box shows icons for CloudFront, Cognito, API Gateway, Lambda (×2, the
     same icon twice), DynamoDB, SQS and SNS. No `service_code / sku` text rows remain (SC-001).
   - Box and VPC names are unchanged.
2. Open an architecture with an EC2 NAT Gateway or EBS SKU.
   - **Expected**: NAT Gateway shows the VPC icon and EBS shows the Elastic Block Store icon, not
     the EC2 icon (product-family override).
3. Click an icon.
   - **Expected**: column 3 opens that service's configuration, and the icon shows a selected ring.
4. Add a SKU from a retired or unmatched service (e.g. `AmazonHoneycode`, if present).
   - **Expected**: the AWS Cloud fallback icon appears, and toggling dark mode switches it to its
     dark variant.

## 4. Hover pop-up (US2)

1. Hover the DynamoDB icon for a PayPerRequest read SKU.
   - **Expected**: the pop-up shows `AmazonDynamoDB`, `Sku: …`, the group description,
     `UsageType: …` and `Operation: PayPerRequestThroughput`, each on its own line.
2. Hover a DynamoDB PITR storage SKU, whose `operation` is empty.
   - **Expected**: there is no `Operation:` line.
3. Hover an EC2 instance SKU.
   - **Expected**: the description line shows the instance-type summary (e.g. `m5.large · 8 GiB ·
     2 vCPU · Linux`).
4. Hover the data-transfer icon.
   - **Expected**: `Sku:` shows the real SKU, and the region-pair label appears as its own line.
5. Tab to an icon with the keyboard.
   - **Expected**: the same pop-up shows, and a screen reader announces the same text.

## 5. Zoom (US3)

1. Zoom in twice, then out four times.
   - **Expected**: icons grow and shrink in step with the box labels (SC-004), and a hovered
     pop-up's text scales to match.
2. Open the pop-out canvas.
   - **Expected**: the icons, pop-up and zoom behave the same way.

## 6. Per-architecture pricing (US4)

1. Clear this site's `localStorage`, reload, open architecture **A**, and click Calculate at
   1 month.
2. Switch to **B**, which has services and has never been calculated.
   - **Expected**: B calculates automatically at 1 month and shows B's total and breakdown
     (FR-017).
3. Set Duration to 1 year and click Calculate on B. Then switch to **A**.
   - **Expected**: A's 1-month result shows immediately with no calculate request in the network
     tab (FR-018, SC-006), and the Duration select changes to 1 month (FR-018b).
4. Switch back to **B**.
   - **Expected**: B's 1-year result, with Duration at 1 year.
5. Reload the page and open **A**.
   - **Expected**: A's result shows immediately with no recalculation (clarification Q1).
6. On **A**, change a service's usage quantity.
   - **Expected**: "Architecture has been updated since last pricing" appears directly below Data
     Timestamp, and nothing recalculates (FR-018a). Change the value back: the notice disappears.
     Click Calculate: the notice disappears and the result updates.
7. Race: switch to a never-calculated architecture **C**, and immediately (under 1 s) switch to
   **A**.
   - **Expected**: A's result stays displayed. Switching to C later shows C's own result (FR-020,
     SC-005).
8. Open an architecture with no services.
   - **Expected**: no automatic request is made, and only the empty state shows.
9. Delete architecture **B**.
   - **Expected**: the `cloud-pricing-result-<B id>` key is gone from `localStorage`.

## 7. Word-wrap toggle (US5)

1. On any calculated result, find the Price per Sku heading.
   - **Expected**: the wrap toggle is on the heading row, right-aligned with the price values, and
     nothing but Data Timestamp (and the notice, when shown) sits below the list.
2. Toggle it.
   - **Expected**: the lines wrap and unwrap exactly as before.
3. Narrow column 5 to its minimum.
   - **Expected**: the heading truncates rather than overlapping the toggle.

## Validation notes (2026-09-25 run)

Run against a local dev server as Admin, on the four standard architectures plus one throwaway
architecture that was created and deleted. §3–§7 behaved as expected, with these findings:

- **Fixed during validation: canvas boxes were measured at the zoomed size.**
  `useMeasuredHeight`'s layout-effect path read `getBoundingClientRect()`, which includes React
  Flow's zoom transform. At the default 0.7 zoom this under-sized boxes and clipped the last row
  of icons (the old text rows were clipped the same way), and when zoomed in it over-sized them.
  It now reads `offsetHeight`, so both measurement paths agree in the box's own coordinates.
- **Fixed during validation: region label overlap.** A full last row of icons ran underneath a
  box's bottom-right region label. The icon row now reserves bottom padding for it.
- **Pre-existing, not addressed here: Price Change after a Duration change is wrong outside
  `us-east-1`.** Repricing the prior selections at the new Duration uses
  `build_transient_architecture`, which pins every selection to `us-east-1`
  (010-multi-region-support). For an architecture in another region the comparison total is
  near $0, so "Price Change" shows roughly the whole price (e.g. Serverless Microservices
  Back-End, `eu-west-1`, 1 month → 1 year showed +1,605.03). A fix would send each selection's
  region with the snapshot request; the stored result's `pricedContents` now records it.
- The pop-up follows canvas zoom as designed, so at high zoom (e.g. 257% after fit-view) it is
  large.
