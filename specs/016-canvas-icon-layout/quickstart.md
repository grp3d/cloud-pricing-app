# Quickstart: Validating 016-canvas-icon-layout

This guide proves the feature works end-to-end. The contracts are in
[contracts/api.md](contracts/api.md) and [contracts/ui.md](contracts/ui.md), and the data shapes
are in [data-model.md](data-model.md).

## Prerequisites

- Local Postgres and the seeded standard architectures (014).
- The real pricing data at `AWS_PRICING_PARQUET_DIR`. Snapshot 2026-09-24 has `_SUCCESS` in all
  five tables; older dates have none.
- The backend (`cd backend && uv run uvicorn src.main:app --reload`) and the frontend from **this
  repo** (`cd frontend && npm run dev`) running. Sign in as Admin.

## 1. Automated checks

```bash
cd backend && uv run pytest
cd frontend && npm run check-api-types && npm run lint && npm test && npm run build
```

**Expected**: everything passes. The CI fixture (`backend/tests/fixtures/pricing_parquet`) has a
`_SUCCESS` in each table's date folder.

## 2. Icons: size, spacing, dragging (US1, US2)

1. Open "Containerized Microservices Platform (EKS)".
   - **Expected**: icons are 60 canvas units across, 3 to a row, 60 apart. The VPC box is 320
     wide and contains every icon, and the region label doesn't overlap anything.
2. Drag an icon within its box and release it on top of another icon.
   - **Expected**: it lands at the nearest free spot, with no overlap.
   - Reload the page. **Expected**: the positions are unchanged.
3. Click an icon without moving it.
   - **Expected**: the service is selected (column 3).
4. In "Active-Standby Multi-Region Web Application", drag a us-east-1 icon into the us-west-2 VPC.
   - **Expected**: it snaps back, and column 2 says it can only move within the same region.
5. Create a VPC and a nested Application in the same region, add a service to the VPC, and drag its
   icon into the Application.
   - **Expected**: the service now appears under the Application in column 2, and the total is
     unchanged.
   - Drag it back up into the VPC. **Expected**: it moves back.
6. Drag a VPC icon around inside the VPC, but not over the nested box.
   - **Expected**: it stays above the nested box, and the nested box moves down as needed.

## 3. Pop-up (US3)

1. Hover an RDS icon.
   - **Expected**: a `databaseEngine: …` line, and no `Operation:` line.
2. Hover an EC2 instance icon.
   - **Expected**: `memory: …` appears once, on its own line, and not in the summary line.

## 4. Errors and placement (US6, US7)

1. Try nesting an Application into a VPC in another region.
   - **Expected**: the error appears in column 2 only.
2. Try creating an architecture whose name is too long.
   - **Expected**: the error appears in column 1 only.
3. Pan the canvas far to one side, then add a top-level collection.
   - **Expected**: it appears fully in view and doesn't overlap existing boxes.

## 5. Active snapshot and Admin System Information (US4, US5)

Use a scratch copy of the pricing data so the real data isn't modified:

```bash
cp -R "$AWS_PRICING_PARQUET_DIR" /tmp/pq && export AWS_PRICING_PARQUET_DIR=/tmp/pq
export SNAPSHOT_CHECK_INTERVAL_SECONDS=15   # speeds up this walkthrough
```

Restart the backend.

1. Open the Admin tab.
   - **Expected**: a "User Management" section, then "System Information" showing active
     2026-09-24, not pinned, and a recent last-checked time.
   - **Expected**: the Issues table lists the fallback services (e.g. AmazonHoneycode), not marked
     New.
2. Copy 2026-09-24 to a new date (e.g. `2026-09-27`) in every table, but **leave out** one table's
   `_SUCCESS`.
   - **Expected**: within 15 s, System Information shows 2026-09-27 as waiting ("no completion
     marker in …"), and pricing still uses 2026-09-24.
3. Add the missing `_SUCCESS`.
   - **Expected**: within 15 s, the active date is 2026-09-27. A new calculation shows Data
     Timestamp 2026-09-27.
4. Create 2026-09-28 with every marker, but delete one `region=` folder from all its tables.
   - **Expected**: it becomes active, and the Issues table has a missing-region line naming that
     region.
5. Set `ACTIVE_SNAPSHOT_DATE=2026-09-20` (no markers) and restart.
   - **Expected**: the server starts, the date shows as pinned, and there's a "pinned snapshot
     incomplete" issue.
6. Set `ACTIVE_SNAPSHOT_DATE=2030-01-01` and restart.
   - **Expected**: the server refuses to start, with a message naming `ACTIVE_SNAPSHOT_DATE`.
7. Clean up: unset the variables, restart, and `rm -rf /tmp/pq`.

## 6. Configuration (US8)

1. Start the backend with `CORS_ALLOWED_ORIGINS='["http://localhost:5180"]'`.
   - **Expected**: a frontend served on :5180 can call the API, and one on :5173 is blocked by CORS.
2. Start the backend with `SNAPSHOT_CHECK_INTERVAL_SECONDS=abc`.
   - **Expected**: startup fails, naming the setting.
3. **Expected**: `docs/configuration.md` lists every setting, its default and its environment
   variable.

## Validation notes (2026-09-26 run)

Run against the dev frontend (:5173) and backend (:8000) as Admin. The snapshot and
configuration steps (§5–§6) ran against a separate scratch backend on :8765+, using a scratch copy
of the CI test data, so the real data and your running server were untouched. §2–§6 behaved as
specified, with these findings:

- **Fixed during validation: default box layout.** Boxes without a saved position used a fixed
  300×260 grid built for 220px-wide boxes. With boxes now up to 380px wide and taller, default-placed
  boxes overlapped (e.g. Active-Standby's two VPCs). Default slots now flow left to right by each
  box's real width, 4 per row, with each row starting below the tallest box of the previous one.
  The gaps are the same as before. Saved positions are unaffected.
- **Fixed during validation: other icons re-flowing.** Dragging one icon made the other
  default-placed icons re-flow to fill the gap. A drop now saves every icon in the boxes involved
  at its current position, so only the dragged icon moves (FR-008).
- **Test timing.** The ServiceIconList pop-up test takes ~5s in jsdom (opening the Radix tooltip),
  as it did before this feature. It now has a 15s timeout instead of failing intermittently.
- **Observed once: first drag after a page load did nothing.** A retry worked, and it didn't recur.
- **Pre-existing, not addressed here: the Admin tab link doesn't navigate.** Clicking "Admin" in
  the top bar leaves the path at `/`; opening `/admin` directly works. It reproduces on the last
  commit before this feature (checked by setting 016's changes aside), so 016 didn't cause it.
