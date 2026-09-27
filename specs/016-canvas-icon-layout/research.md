# Phase 0 Research: Canvas Icon Layout, Active Pricing Snapshot & Configurable Settings

The spec has no open clarifications. The decisions below come from the current codebase, the
real pricing data (`DATA/pricing_aws/parquet`, which has 22 snapshot dates, only 2026-09-24
marked `_SUCCESS`), and the choices recorded in spec.md › Clarifications.

---

## 1. Active snapshot date: where it lives and how lookups use it

**Finding**: Every pricing lookup calls `pricing_data/snapshot.py::resolve_latest_snapshot_date()`,
which rescans all five table folders on every call. There are 7 call sites, in `catalog.py`,
`pricing.py`, `regions.py` and `price_calculation.py`. One request can call it several times:
`attach_units_to_architecture` resolves units and product details once per region, and each of
those resolves the date again.

**Decision**:
- A new module, `backend/src/pricing_data/active_snapshot.py`, holds an in-process
  `ActiveSnapshotState`: the active date, whether it is pinned, the time of the last check, any
  waiting snapshots, the current issues, and the active date's marker times.
- `get_active_snapshot_date()` replaces `resolve_latest_snapshot_date()` at every call site. It
  reads the in-memory value. On first use, if nothing is initialized yet, it runs one check
  synchronously. That makes it work in tests and scripts that don't start the app's lifespan. If
  no active date can be determined, it raises `PricingDataUnavailableError`, so the existing 503
  handler covers that case.
- FR-019 (one date per request): each request-level entry point reads the active date once and
  passes `snapshot_date=` down explicitly. Those entry points are `calculate_architecture_price`
  (already does this), `attach_units_to_architecture` / `sku_selection_out_with_unit`,
  `search_catalog`, and `list_regions`. The lower-level lookups already accept `snapshot_date`.
- `resolve_latest_snapshot_date()` is removed rather than left alongside, so no lookup can still
  pick its own date (FR-014). A test asserts nothing in `src/` references it.

**Rationale**: This is the smallest change that makes the active date the single source of truth.
It removes per-request folder scans, and keeps the existing error mapping.

**Alternatives considered**:
- *A FastAPI dependency that injects the date into every route*: rejected. Lookups are also called
  from services and scripts, not only from routes.
- *Storing the active date in Postgres*: rejected, per Clarification Q4 (no persistence in this
  feature).

## 2. Deciding which snapshot is active

**Decision**: `check_snapshots(parquet_dir, state, override) -> CheckResult` is a pure function
over the filesystem.
- **Complete date**: a date is complete when `<table>/snapshot_date=<D>/_SUCCESS` exists in all
  five tables.
- **Candidate**: the newest complete date. If it is newer than the active date, it becomes active
  (FR-015).
- **Waiting snapshots**: every date newer than the active one that isn't complete is reported as
  waiting (FR-021), with a reason. Possible reasons:
  - "missing from price_fact, region_dim"
  - "no completion marker in product_dim"
- **Override** (`ACTIVE_SNAPSHOT_DATE`), validated at startup:
  - If the date's folder is missing from any table, the app raises and refuses to start
    (FR-018/FR-026).
  - If the date exists everywhere but has no marker in some table, the date is accepted and a
    "pinned snapshot incomplete" issue is recorded.
  - While pinned, the background check still refreshes the waiting list and the last-check time,
    but never changes the date.
- **In-place update** (FR-023): the check stores each table's `_SUCCESS` modification time for the
  active date. Any change triggers the icon analysis again. The markers are 0 bytes, so only the
  timestamp can signal a change.
- **Unreadable data folder**: the active date is kept. The error is logged and appears on the
  Admin tab as the last check's error (edge case).

**Rationale**: Checking markers is O(tables × dates) with cheap directory listings, and needs no
Parquet reads. Keeping it pure makes it straightforward to unit-test against a temporary folder.

## 3. Missing-region check and the "New" marker

**Decision**:
- **Missing regions** (FR-016, Clarification Q4): only when the active date switches while the
  server is running. The check compares the union of `region=*` folders across the five tables for
  the old date against the new date. Any region that's gone is recorded as an issue, stored in
  memory, so it's lost on restart as the spec accepts.
- **"New" marker** (spec Assumptions): a service is marked New if its code isn't in the service
  codes of the next-older date that exists in all five tables, whether or not that date has
  markers. That date is read from `service_dim`. Nothing needs to be persisted.

## 4. Icon analysis: sharing the mapping with the backend

**Finding**: The mapping only exists as the frontend file `awsServiceIcons.generated.ts`
(015), which the backend can't read.

**Decision**:
- `generate_aws_service_icon_map.py` also writes `backend/src/pricing_data/aws_service_icons.json`
  in the same run, containing the same maps. That JSON is the backend's copy.
- A backend test checks the JSON and the TS against each other, parsing the TS object literals
  with a small regex, since both files are generated.
- `pricing_data/icon_coverage.py::find_unmatched_services(snapshot_date, previous_date)` reads
  `service_dim` for the active date, which holds service code and name, and returns every code
  that:
  - is not in `BY_CODE`,
  - is not `AWSDataTransfer`, and
  - has no family override (a family override only refines a code that is already mapped).

  Each result carries `is_new` (§3).

**Rationale**: FR-023 requires the Issues table and the canvas to agree. Generating both files
from one run guarantees that, and the test catches hand edits.

**Alternatives considered**:
- *Serving the mapping from the backend and fetching it in the frontend*: rejected. It adds a
  runtime dependency and a loading state to every canvas render.
- *The backend reading the frontend's TS file*: rejected. It couples the backend to the frontend's
  directory layout, and breaks in a deployment that ships only the backend.

## 5. Background service

**Decision**:
- An `asyncio` task is started from a new FastAPI `lifespan` in `main.py`.
- **At startup**, before serving, lifespan runs one check (FR-017). That check validates the
  override and does the startup icon analysis.
- **Then**, a loop runs `await asyncio.sleep(settings.snapshot_check_interval_seconds)` (default
  300) followed by `await asyncio.to_thread(run_check)`.
- **No overlapping checks**: the loop is sequential, so a slow check pushes the next one back
  instead of overlapping it. An `asyncio.Lock` also protects against a manual trigger added later.
- **Shutdown**: lifespan cancels the task.
- **Failures** are caught and logged. A failed check never stops the loop.

**Rationale**: This needs no new dependency (Principle VI; APScheduler was rejected), and keeps
everything in one process, as the spec's Assumptions allow.

## 6. Moving a service to another box (FR-004a/b)

**Finding**: `PATCH /sku-selections/{id}` only updates pricing inputs. No endpoint moves a
selection between collections.

**Decision**: add an optional `collection_id` to `SKUSelectionUpdate`. When it is set:
- The selection must currently belong to a collection. Connector-owned selections return `400`.
- The target collection must belong to the same architecture, which the user owns, and must not
  be deleted. Otherwise the endpoint returns `404`.
- The target's region must equal the source collection's region. Otherwise it returns `409` with
  `{"error":"region_mismatch","message":"<service> can only move to a box in <region>"}`.
  Column 2 shows that message.

Moving the service is a Postgres write to user-defined data (Principle II), so the test comes
first (Principle V). Prices are unchanged, because the region is the same. 015's out-of-date check
ignores which collection a service is in, so the "updated since last pricing" notice correctly
doesn't appear.

## 7. Icon layout on the canvas

**Decision**: a pure module, `frontend/src/lib/iconLayout.ts`, with:
- **Constants**:
  - `ICON = 60` (2.5 × 24)
  - `GAP = 60` (one icon width; initially 90, reduced after review because boxes spread too far)
  - `MAX_PER_ROW = 3`
  - `PAD = 8`, matching the box's `p-2`
- `defaultBoxWidth(count, minWidth)`: the larger of today's default and
  `PAD*2 + n*ICON + (n-1)*GAP + border`, where n = min(count, 3). For 3 icons that's 320px.
- `defaultPositions(ids, innerWidth)`: places icons row by row, with up to 3 per row that fit
  `innerWidth`, spaced `ICON + GAP` apart.
- `isValidSpot(pos, others)`: true when `pos` is at least `GAP` from every other icon in both
  directions. Icons are axis-aligned squares, so the rule is "separated by ≥ GAP horizontally or
  vertically".
- `nearestValidSpot(pos, others, bounds)`: searches a grid of candidate spots in widening rings
  around the drop point, with a step of ICON/4, and picks the closest valid one inside the bounds.
- `resolvePositions(ids, saved, innerWidth)`: saved positions are kept when still valid. New or
  invalid ones get the first free default slot (FR-008, edge cases).
- `contentHeight(positions)`: the height the icon area needs.

**Box sizing**: icons are absolutely positioned inside an icon area whose height is
`contentHeight + label reserve`. The box height is still measured from the DOM (`useMeasuredHeight`,
fixed in 015), so the box grows automatically. VPCs keep their own-services area above the nested
boxes (§8).

**Rationale**: all the geometry is in pure, test-first functions, following the existing pattern
in `nodeLayout.ts` and `dropTargetDetection.ts`.

## 8. Dragging icons

**Decision**:
- **Events**: pointer events on the icon button, with React Flow's `nodrag nopan` classes so that
  dragging an icon doesn't drag the box or pan the canvas.
- **Click vs drag**: movement of 4 screen px or less counts as a click (FR-007).
- **During the drag**: the icon follows the pointer via
  `screenToFlowPosition` (from `useReactFlow`), which works at any zoom. It's rendered in a raised
  layer so it doesn't show behind other boxes.
- **On drop**:
  - Hit-test node rects in flow space, deepest first, so a nested Application beats its VPC.
  - If the target is the icon's own box: `nearestValidSpot`, then save the position.
  - If the target is a different box in the same region: call the move endpoint, then save the
    icon's position under that box. The icon is shown in the target box before the server replies,
    and is rolled back if the call fails (error in column 2).
  - Otherwise (a different region, or no box): snap back. A different region shows the
    region-mismatch message in column 2 without calling the server.
- **VPC own-services area**: a drop inside the VPC but not over a nested box is clamped to the
  own-services area, which then grows. The nested boxes' y-offsets come from `childYOffsets`,
  which already reads the measured own-content height, so they shift down on their own.
- **Persistence**: `frontend/src/lib/iconLayoutStorage.ts` stores
  `cloud-pricing-icon-layout-<architectureId>` → `{ [skuSelectionId]: {x, y} }` (relative to the
  box's icon area), using the same `localStorage` + try/catch + type-guard pattern as
  `diagramLayout.ts`. Positions are per browser (spec Assumptions). Moving a service to another
  box keeps the same key, so its position simply applies inside the new box.

## 9. Pop-up attribute lines (FR-009–FR-011)

**Decision**:
- `servicePopup.ts` drops the `Operation:` line.
- It adds `POPUP_ATTRIBUTE_KEYS`, the 15 keys in the spec's order, each rendered as
  `key: value` when the SKU has a non-empty value.
- The summary line becomes `summarizeAttributes(attributes, { exclude: POPUP_ATTRIBUTE_KEYS })`
  (a new optional parameter), so a value like memory appears only once.
- `CatalogSearchPanel` and the other callers are unchanged.

## 10. Errors in the right column (FR-012)

**Finding**: `WorkspacePage.tsx` has one `actionError` state, passed to both
`ProviderArchitecturePanel` (column 1) and `CollectionsPanel` (column 2). The nesting-region
message is set at lines 893/969 into the same state.

**Decision**: split it into two states:
- `architectureActionError`, used by `createArchitecture`, `deleteArchitecture`, `toggleArchitecturePublic`
  and `importArchitecture`;
- `collectionActionError`, used by collection, connector, nesting and region actions, and by icon
  moves.

Each panel gets its own state and dismiss handler. The existing `skuActionError` for column 3 is
unchanged.

## 11. Placing new collections in view (FR-013)

**Finding**: top-level collections without a saved layout get a grid slot (`(i % 4) * 300`,
`floor(i / 4) * 260`) whatever the viewport is showing.

**Decision**: in `ArchitectureDiagramPanel`, track which top-level collection ids have been seen
since the architecture loaded. When a new one appears without a saved layout:
1. Compute the visible flow-space rect from the viewport (`x`, `y`, `zoom`) and the canvas size.
2. Call a pure `findVisibleSlot(visibleRect, occupiedRects, boxSize, margin)` in
   `frontend/src/lib/newNodePlacement.ts`. It scans a grid across the visible rect and returns the
   first rect that is fully visible and doesn't overlap an existing box. If there is none, it
   returns the visible top-left (FR-013, US7 scenario 3).
3. Save the result with `writeCollectionLayout`, so the placement survives a reload.

Collections present on the first load keep today's behavior. Nested collections are unchanged.

## 12. Configuration (FR-025–FR-027)

**Finding**: `src/config.py` already uses `pydantic-settings` (`BaseSettings`, `.env`), exposing
`database_url`, `aws_pricing_parquet_dir` and `aws_pricing_region`. Values that are fixed in code
elsewhere:
- CORS origin `http://localhost:5173` (`main.py`)
- catalog search default and maximum page size, 50 and 200 (`api/catalog.py`)
- password hashing iterations, 260 000 (`auth_service.py`)
- logging level INFO (`main.py`)
- the snapshot check interval and override (new in this feature)

Two are kept as code constants because they're format or physics, not operational:
`EXPORT_FORMAT` (a file-format identifier) and `_HOURS_PER_DAY`. The five table names are the
upstream data layout, and stay constants.

**Decision**: add these fields to `Settings`, with defaults equal to today's behavior:

| Field | Default |
|---|---|
| `cors_allowed_origins: list[str]` | `["http://localhost:5173"]` |
| `catalog_search_default_limit: int` | `50` |
| `catalog_search_max_limit: int` | `200` |
| `password_hash_iterations: int` | `260000` |
| `log_level: str` | `"INFO"` |
| `snapshot_check_interval_seconds: int` | `300` (must be > 0) |
| `active_snapshot_date: date \| None` | `None` |

- Environment variable names follow `pydantic-settings`' default of the upper-cased field name
  with no prefix, matching the existing `DATABASE_URL` and `AWS_PRICING_PARQUET_DIR`.
- List values are read as JSON (`CORS_ALLOWED_ORIGINS='["http://a","http://b"]'`).
- Pydantic validation errors stop startup and name the field (FR-026).

**Documentation**: `docs/configuration.md` holds the table of settings, defaults and environment
variables, and there's a checked-in `backend/.env.example` (FR-027).

**Note**: `password_hash_iterations` applies to new hashes only. `verify_password` already reads
each stored hash's own iteration count (`pbkdf2_sha256$<iterations>$…`), so changing the setting
doesn't lock anyone out; a test pins this.

## 13. Admin tab

**Decision**:
- **Backend**: `GET /api/v1/admin/system-info` (admin only; `require_admin` from `deps.py`) returns
  the in-memory state (contracts/api.md).
- **Frontend**: `AdminPage.tsx` wraps today's content in a "User Management" section and adds a
  `SystemInformationSection` component. It shows:
  - the active date, with a "pinned" badge when pinned;
  - the last check time, in local time;
  - the waiting snapshots, with their reasons;
  - the Issues table, with columns Type · Detail · Snapshot · New.

  The data is fetched with TanStack Query and refetched every 60 seconds while the page is open.

## 14. Testing approach

- **Backend (test-first, Principle V)**:
  - `check_snapshots`, against a temporary parquet tree:
    - chooses the newest complete date;
    - reports incomplete dates as waiting, with reasons;
    - override: a missing date fails, a date without markers gives a warning issue;
    - detects a changed marker time;
    - handles an unreadable folder;
    - records missing regions on a switch.
  - `find_unmatched_services`, including `is_new`.
  - The generated-map consistency test (§4).
  - Contract tests for `GET /admin/system-info` (admin only, response shape).
  - Contract tests for `PATCH /sku-selections/{id}` with `collection_id`: success, cross-region
    `409`, other-architecture `404`, connector-owned `400`.
  - Settings tests: environment overrides and invalid values.
  - A test that no module references `resolve_latest_snapshot_date`.
- **CI fixture**: `build_test_pricing_fixture.py` must write `_SUCCESS` into each table's date
  folder, and the committed fixture must be regenerated, or CI will have no active snapshot.
- **Frontend (test-first for pure logic)**:
  - `iconLayout`: default positions, width, validity, nearest spot, resolving saved positions.
  - `newNodePlacement`.
  - `servicePopup` (the new lines, no Operation line, deduplicated summary).
  - `iconLayoutStorage`.
  - Component tests: icons at 60px and positioned; errors split by column; the Admin System
    Information section.
- **Manual (quickstart.md)**: dragging within a box, across boxes, and cross-region; placing a new
  collection in view; switching snapshots with and without markers; the override.
