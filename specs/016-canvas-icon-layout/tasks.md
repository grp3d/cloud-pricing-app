---

description: "Task list for 016-canvas-icon-layout"
---

# Tasks: Canvas Icon Layout, Active Pricing Snapshot & Configurable Settings

**Input**: Design documents from `specs/016-canvas-icon-layout/`

**Prerequisites**:
- plan.md
- spec.md
- research.md
- data-model.md
- contracts/api.md
- contracts/ui.md
- quickstart.md

**Tests**: Included. Tests marked "(write first)" MUST be seen failing before the task they cover (Constitution Principle V). They cover:
- the snapshot-selection logic;
- the icon-coverage analysis;
- the SKU-move endpoint (a Postgres write);
- settings validation;
- the pure frontend geometry modules.

Presentational component tests may follow implementation.

**Organization**: One phase per user story, in priority order. The P1 stories come first: US1, US4, US6 and US7. Then P2: US2, US3 and US5. Then P3: US8.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**:
  - US1: larger, spaced icons
  - US2: dragging icons
  - US3: pop-up
  - US4: active snapshot
  - US5: Admin system information
  - US6: error columns
  - US7: new-box placement
  - US8: configuration
- Paths are relative to the repository root.

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 [P] Extend `backend/scripts/build_test_pricing_fixture.py` so that `build()` writes an empty `_SUCCESS` file into `<out>/<table>/snapshot_date=<date>/` for every table after copying. Then re-run it (`cd backend && uv run python scripts/build_test_pricing_fixture.py --source "$AWS_PRICING_PARQUET_DIR" --snapshot-date 2026-09-24`). Commit the regenerated `backend/tests/fixtures/pricing_parquet/**` including the five `_SUCCESS` files. Confirm that `uv run pytest` still passes against the fixture (`AWS_PRICING_PARQUET_DIR=backend/tests/fixtures/pricing_parquet`).
- [X] T002 [P] Extend `backend/scripts/generate_aws_service_icon_map.py` to also write `backend/src/pricing_data/aws_service_icons.json`, keeping the deterministic output:
  - shape `{"by_code": {...}, "by_code_and_family": {...}, "special_codes": ["AWSDataTransfer"]}`;
  - sorted keys and a trailing newline.

  Re-run the script (`--icons ../../images-web/aws_architecture_icons`). Confirm that the TS output is byte-identical to before, and commit the new JSON.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Settings fields and shared test helpers that both the active-snapshot work (US4) and the configuration work (US8) build on.

- [X] T003 Add a test helper `backend/tests/helpers/parquet_tree.py` with `make_snapshot_tree(root: Path, dates: dict[str, dict]) -> Path`. It builds a fake five-table tree under `root`: `<table>/snapshot_date=<d>/region=<r>/`, with an optional `_SUCCESS` per table. Per date it takes `tables_missing`, `markers_missing` and `regions`, and it optionally writes a minimal `service_dim` parquet with `(service_code, service_name)` rows using DuckDB `COPY`. Add `backend/tests/helpers/__init__.py`.
- [X] T004 (write first) Create `backend/tests/unit/test_settings.py` with failing tests for these new `Settings` fields in `backend/src/config.py`, instantiated with `Settings(_env_file=None)` and `monkeypatch.setenv`:
  - `snapshot_check_interval_seconds` defaults to 300, reads `SNAPSHOT_CHECK_INTERVAL_SECONDS`, and rejects `abc` and values below 10 with a `ValidationError` naming the field;
  - `active_snapshot_date` defaults to `None`, parses `ACTIVE_SNAPSHOT_DATE=2026-09-20` to a `date`, and rejects `not-a-date`.
- [X] T005 Add `snapshot_check_interval_seconds: int = Field(300, ge=10)` and `active_snapshot_date: date | None = None` to `Settings` in `backend/src/config.py`, with comments citing 016 FR-015 and FR-018. This makes T004 pass.

**Checkpoint**: the fixture has markers, the backend icon JSON exists, and the snapshot settings exist.

---

## Phase 3: User Story 1: Larger, well-spaced service icons (Priority: P1) 🎯 MVP

**Goal**:
- Icons are 60px.
- Default placement is 3 per row, 60px apart (reduced from 90px after review).
- Boxes widen to fit (320px for 3), and are never narrower than today's defaults.
- Nothing overlaps the box name or region label.

**Independent Test**: quickstart §2 step 1. On the EKS architecture, icons are 60 across, 3 to a row and 60 apart, and the VPC box contains them all with no clipping.

### Tests (write first)

- [X] T006 [P] [US1] Create `frontend/tests/unit/iconLayout.test.ts` for `frontend/src/lib/iconLayout.ts`. It checks these constants: `ICON=60`, `GAP=60`, `MAX_PER_ROW=3`, `PAD=8`, `LABEL_RESERVE=16`. It tests:
  - `defaultBoxWidth(count, minWidth)`:
    - 0 or 1 icon → `minWidth` (220 for a VPC, 200 for an Application);
    - 2 icons → `max(minWidth, 2*PAD + 2*ICON + GAP + 4)`;
    - 3 or more icons → `2*PAD + 3*ICON + 2*GAP + 4` (= 320 with borders).
  - `defaultPositions(ids, innerWidth)`:
    - row-major order;
    - `x` values are 0, 120 and 240;
    - wraps after 3, or earlier when `innerWidth` is narrower (e.g. 1 per row at 60);
    - rows are 120 apart.
  - `isValidSpot(p, others)`: true when, for every other icon, |dx| ≥ ICON+GAP or |dy| ≥ ICON+GAP; false for anything closer.
  - `nearestValidSpot(p, others, bounds)`:
    - returns `p` when it is valid;
    - otherwise returns the closest valid spot inside `bounds` (a deterministic tie-break);
    - never returns a spot outside `bounds.width`, and extends downward (the height is unbounded).
  - `contentHeight(positions)` = max(y) + ICON + LABEL_RESERVE, or 0 for none.

### Implementation

- [X] T007 [US1] Implement `frontend/src/lib/iconLayout.ts` per T006 and research.md §7: pure functions, no DOM, with a module comment citing 016 FR-001–FR-003. This makes T006 pass.
- [X] T008 [US1] In `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`, render the icons:
  - Change `ServiceIconButton` to `size-[60px]` (the button and its `<img>`).
  - Change `ServiceList` from a flex-wrap row to a `relative` icon area whose `height` is `contentHeight(positions)`. Each button is absolutely positioned at `defaultPositions(ids, innerWidth)`.
  - Pass `innerWidth` (the box width − 2·PAD − borders) in from the node components.
  - Remove the 015 `pb-3`, which is now covered by `LABEL_RESERVE`.
- [X] T009 [US1] In `ArchitectureDiagramPanel.tsx`'s `initialNodes` memo:
  - Replace the fixed widths (VPC 220, Application 200, nested 180) with `defaultBoxWidth(c.sku_selections.length, <today's width>)` wherever there is no manual width.
  - Keep a manual override's width, but never below the one-icon minimum (`2*PAD + ICON + borders`), per spec Edge Cases.
  - A VPC must also be at least as wide as its widest nested child plus the 20px child inset.
  - The measured-height path (`useMeasuredHeight`) stays the height authority.
- [X] T010 [P] [US1] Update `frontend/tests/unit/ServiceIconList.test.tsx`:
  - Buttons have the 60px classes.
  - For 4 selections, the 4th button's inline `top` is 120 and its `left` is 0.
  - The icon area's height equals `contentHeight`.
  - Keep the existing click, selection and tooltip tests.

**Checkpoint**: US1 works on its own.

---

## Phase 4: User Story 4: Pricing always uses one complete snapshot (Priority: P1)

**Goal**:
- One in-memory active snapshot date, used by every pricing lookup.
- It switches only to dates with `_SUCCESS` in all five tables.
- The override setting pins it.
- It is checked at startup and then every `SNAPSHOT_CHECK_INTERVAL_SECONDS` by an asyncio task.
- A switch records missing regions.

**Independent Test**: quickstart §5 steps 2, 3 and 5–6. A date without markers waits, then becomes active once the markers are added. The override pins a date. A pinned date that doesn't exist stops startup.

### Tests (write first)

- [X] T011 [P] [US4] Create `backend/tests/unit/test_active_snapshot.py` using `make_snapshot_tree` (T003). It needs failing tests for `check_snapshots(parquet_dir, state, override, *, at_startup)` in `backend/src/pricing_data/active_snapshot.py`:
  - **(a)** It picks the newest date that has markers in all five tables.
  - **(b)** A newer date missing a table → waiting with reason `"missing from price_fact"`. A newer date missing a marker → `"no completion marker in product_dim"`. Neither is picked.
  - **(c)** A running switch from D1 (regions a, b) to D2 (region a) records one `missing_regions` issue with `regions == ["b"]`. The same tree at startup records none.
  - **(d)** Override on a date present everywhere with no markers → active and `pinned`, with one `pinned_incomplete` issue. Override on a date missing from a table → raises `ActiveSnapshotConfigError`, whose message contains `ACTIVE_SNAPSHOT_DATE`.
  - **(e)** While pinned, a newer complete date → the active date doesn't change, and the newer date isn't listed as waiting (it's complete).
  - **(f)** No complete date and no override → `active_date is None`, and `last_check_error` explains why.
  - **(g)** It returns `analysis_needed=True` on a switch, at startup, and when an active-date `_SUCCESS` mtime changes (`os.utime`), and `False` otherwise.
  - **(h)** An unreadable/missing `parquet_dir` → keeps the previous `active_date` and sets `last_check_error`.
  - **(i)** `last_check_at` is set on every run.
- [X] T012 [P] [US4] In the same file, add tests for `get_active_snapshot_date()`:
  - It returns the state's date.
  - It lazily runs one check when the state is uninitialized (monkeypatch `settings.aws_pricing_parquet_dir` to a tmp tree).
  - It raises `PricingDataUnavailableError` when there is no active date.
- [X] T013 [P] [US4] Add `backend/tests/unit/test_no_latest_snapshot_scan.py`, asserting that no file under `backend/src/` contains `resolve_latest_snapshot_date`. This covers FR-014.

### Implementation

- [X] T014 [US4] Implement `backend/src/pricing_data/active_snapshot.py` per data-model.md §1–2 and research.md §1–3:
  - dataclasses `ActiveSnapshotState`, `WaitingSnapshot`, `Issue` and `CheckResult`;
  - `ActiveSnapshotConfigError`;
  - the pure-ish `check_snapshots(parquet_dir, state, override, *, at_startup) -> CheckResult`, which mutates and returns the state and reports `analysis_needed`;
  - a module-level `STATE` and `_lock = threading.Lock()`;
  - `run_check(*, at_startup=False)`, which calls `check_snapshots` under the lock, then (when `analysis_needed`) calls the icon analysis from T031 via an injectable hook that defaults to a no-op until US5;
  - `get_active_snapshot_date() -> str`, which lazily initializes and raises `PricingDataUnavailableError` when `None`.

  Move the five-table tuple into `backend/src/pricing_data/snapshot.py` as the shared `TABLES`, and delete `resolve_latest_snapshot_date`. Together these make T011–T012 pass.
- [X] T015 [US4] Replace every `resolve_latest_snapshot_date()` call with `get_active_snapshot_date()`:
  - `backend/src/pricing_data/catalog.py` (3 sites)
  - `backend/src/pricing_data/pricing.py` (3)
  - `backend/src/pricing_data/regions.py` (1)
  - `backend/src/services/price_calculation.py` (1)

  Update the docstrings that mention the old function. This makes T013 pass.
- [X] T016 [US4] FR-019 (one date per request). **First (write first, see it fail):** add a test to `backend/tests/unit/test_active_snapshot.py` that monkeypatches `get_active_snapshot_date` (as imported by `architecture_service`) to return `"2026-09-24"` on its first call and `"2026-09-25"` on every later call. Then spy on `resolve_units` and `resolve_product_details`, call `attach_units_to_architecture` for an architecture with collections in two regions (built in memory; no DB needed), and assert every spied call received `snapshot_date="2026-09-24"`. **Then:** in `backend/src/services/architecture_service.py`, have `attach_units_to_architecture` and `sku_selection_out_with_unit` call `get_active_snapshot_date()` once and pass `snapshot_date=` to every `resolve_units`/`resolve_product_details` call. Also pass it through `_region_grouped_batch_resolve`. `price_calculation.py` already resolves once, so verify that it keeps passing the date down.
- [X] T017 [US4] Add a FastAPI `lifespan` in `backend/src/main.py` and pass it to `FastAPI(...)`:
  - **Startup**: `run_check(at_startup=True)` in a thread. `ActiveSnapshotConfigError` is re-raised, so the server refuses to start.
  - **Background**: start `asyncio.create_task(_snapshot_monitor())`, which loops `await asyncio.sleep(settings.snapshot_check_interval_seconds)` then `await asyncio.to_thread(run_check)`. It catches and logs any exception per iteration and never exits.
  - **Shutdown**: cancel and await the task.
- [X] T018 [US4] Run `cd backend && uv run pytest`. Every existing test must pass against both the real data and `AWS_PRICING_PARQUET_DIR=tests/fixtures/pricing_parquet`. Fix any test that relied on the old per-call scan.

**Checkpoint**: pricing uses the active snapshot; quickstart §5 steps 2, 3, 5 and 6 work.

---

## Phase 5: User Story 6: Errors appear only in the column they belong to (Priority: P1)

**Goal**: architecture-action errors show in column 1 only, and collection/connector/nesting/move errors show in column 2 only.

**Independent Test**: quickstart §4 steps 1–2.

- [X] T019 [US6] In `frontend/src/pages/WorkspacePage.tsx`, replace `actionError`/`setActionError` with two states:
  - `architectureActionError`, set by `createArchitecture`, `deleteArchitecture`, `toggleArchitecturePublic` and `importArchitecture`;
  - `collectionActionError`, set by `createCollection`, `deleteCollection`, `createConnector`, `deleteConnector`, `updateCollectionParent`, `updateCollectionRegion`, and the two cross-region nesting messages (currently around lines 893 and 969).

  Pass `architectureActionError` and its own dismiss handler to `ProviderArchitecturePanel`, and `collectionActionError` and its own dismiss handler to `CollectionsPanel`. Cite 016 FR-012 in a comment.
- [X] T020 [P] [US6] Create `frontend/tests/unit/WorkspacePage.errors.test.tsx`, using the same harness as `WorkspacePage.pricing.test.tsx` with mocked `api`:
  - **(a)** `api.createArchitecture` rejects → the message appears once, inside column 1's panel (query within the `ProviderArchitecturePanel` container), and not in column 2.
  - **(b)** A column-2 action (`api.deleteCollection` rejects) → the message appears only in column 2.
  - **(c)** Dismissing in one column leaves the other column's error in place.

---

## Phase 6: User Story 7: New collections appear where the user can see them (Priority: P1)

**Goal**: a new top-level box is placed fully in view, without overlapping other boxes when possible, and the placement is saved.

**Independent Test**: quickstart §4 step 3.

### Tests (write first)

- [X] T021 [P] [US7] Create `frontend/tests/unit/newNodePlacement.test.ts` for `findVisibleSlot(visible, occupied, size, margin=24)` in `frontend/src/lib/newNodePlacement.ts`. `visible`, `occupied` and the result are `{x, y, width, height}`.
  - **(a)** Empty canvas → the visible top-left plus margin.
  - **(b)** Scans left-to-right, top-to-bottom in steps of `size + margin`, and returns the first rect that is fully inside `visible` and doesn't intersect any occupied rect (inflated by margin).
  - **(c)** Visible area fully occupied → the visible top-left plus margin (overlap allowed).
  - **(d)** A box larger than the visible area → the visible top-left.

### Implementation

- [X] T022 [US7] Implement `frontend/src/lib/newNodePlacement.ts` per T021. It is pure, with a comment citing 016 FR-013. This makes T021 pass.
- [X] T023 [US7] In `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`:
  - Keep a `seenTopLevelIdsRef`, initialized with the top-level collection ids on the first render after the architecture's data loads. Reset it to empty whenever `architectureId` changes, and refill it once the new architecture's data has loaded, so an architecture you switch to never has its existing boxes treated as new.
  - When a top-level collection id appears that isn't in the ref and has no `manualSizeRef` entry:
    1. Compute the visible flow rect from `useViewport()` (x, y, zoom) and the canvas container's measured size (`useMeasuredWidth` or the React Flow wrapper's `getBoundingClientRect`).
    2. Call `findVisibleSlot` with the other top-level nodes' rects and the new box's default size.
    3. Store `{x, y, width, height}` via `writeCollectionLayout` and in `manualSizeRef`, then add the id to the ref.
  - Collections present on first load keep the existing grid fallback, and nested collections are unchanged.

---

## Phase 7: User Story 2: Drag icons within and between boxes (Priority: P2)

**Goal**:
- Icons can be dragged to hand-placed positions (saved per browser).
- Dropping into another same-region box moves the service.
- Cross-region and empty-canvas drops snap back.
- VPC icons stay above nested boxes unless dropped into one.

**Independent Test**: quickstart §2 steps 2–6.

**Depends on**: US1 (`iconLayout.ts`, the positioned icon area).

### Tests (write first)

- [X] T024 [P] [US2] Extend `backend/tests/contract/test_sku_selections.py` with the contracts/api.md §2 cases:
  - **(1)** A move between two same-region Application boxes in one architecture → 200, and `GET /architectures/{id}` shows the selection under the target.
  - **(2)** A target in another region → 409 with `error == "region_mismatch"`, and no change.
  - **(3)** A target in another architecture owned by the same user → 404.
  - **(4)** A connector-owned selection (attach via `POST /connectors/{id}/sku-selection`) → 400 with `error == "not_movable"`.
  - **(5)** Moving to the same box → 200, unchanged.
  - **(6)** Another user's target collection → 404.
- [X] T025 [P] [US2] Create `frontend/tests/unit/iconLayoutStorage.test.ts` for `readIconLayout(architectureId)`, `writeIconPosition(architectureId, selectionId, pos)` and `removeIconPosition(...)` in `frontend/src/lib/iconLayoutStorage.ts`:
  - key `cloud-pricing-icon-layout-<id>`;
  - a round-trip;
  - per-entry tolerance (an invalid entry is dropped, the others are kept);
  - no throws when storage throws.
- [X] T026 [P] [US2] Extend `frontend/tests/unit/iconLayout.test.ts` with `resolvePositions(ids, saved, innerWidth)`:
  - valid saved positions are kept;
  - a saved position that overlaps another, or is out of bounds, is replaced by the first free default slot;
  - new ids go to the first free default slot without moving the saved ones (FR-008).

  Also add `clampToArea(pos, area)`.

### Implementation

- [X] T027 [US2] Backend move:
  - Add `collection_id: uuid.UUID | None = None` to `SKUSelectionUpdate` in `backend/src/models/schemas.py`.
  - In `backend/src/api/sku_selections.py`'s `update_sku_selection`, when `body.collection_id` is set:
    1. Reject a connector-owned selection with 400 `{"error":"not_movable",...}`.
    2. Load the target with `get_owned_collection` (404 when missing, deleted or not owned). Require the same `architecture_id`, else 404.
    3. Compare regions and return 409 `{"error":"region_mismatch","message": ...}` per contracts/api.md.
    4. Set `selection.collection_id`, and resolve the output with the target's region.
  - Return JSON error bodies via `JSONResponse`, matching the existing error style.

  This makes T024 pass. Then regenerate `frontend/src/api/generated/schema.d.ts` against a running backend (`openapi-typescript http://localhost:<port>/openapi.json -o src/api/generated/schema.d.ts`), and extend `api.updateSkuSelection` in `frontend/src/api/client.ts` to accept `collection_id`.
- [X] T028 [US2] Implement `frontend/src/lib/iconLayoutStorage.ts` per T025, and add `resolvePositions`/`clampToArea` to `frontend/src/lib/iconLayout.ts` per T026. This makes both pass.
- [X] T029 [US2] In `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`, add icon dragging:
  - **Pointer handling**: `ServiceIconButton` gets `className="nodrag nopan"` and pointer handlers with pointer capture on `pointerdown`. Movement of 4 screen px or less is a click (the existing `onSelectService`). Beyond that, it is a drag: the icon follows `screenToFlowPosition(pointer)`, and is rendered above every box via a fixed-position drag ghost or `z-index` on the node wrapper.
  - **On release**, hit-test the drop point against the nodes' absolute flow rects (`useReactFlow().getNodes()`, using `positionAbsolute`/`measured`), deepest first:
    - **Own box**: `nearestValidSpot`, with the VPC own-services area clamp when the box is a VPC and the point isn't over a nested child. Then `writeIconPosition`.
    - **Other box, same region** (compare `data.region`): call a new `onMoveService(selectionId, targetCollectionId, positionInTarget)` prop, and optimistically record the position.
    - **Other box, different region**: snap back, and call `onMoveRejected(message)`.
    - **Empty canvas**: snap back.
  - **Positions**: build them from `resolvePositions(ids, readIconLayout(architectureId), innerWidth)`, and re-read after writes via state. Clamping VPC-owned icons to the own-services area needs no separate constraint beyond T008's icon-area height, which already pushes children down through the measured height.
- [X] T030 [US2] In `frontend/src/pages/WorkspacePage.tsx`:
  - Add a `moveService` mutation that calls `api.updateSkuSelection(id, { collection_id })`. `onSuccess` invalidates the architecture query; `onError` calls `setCollectionActionError(errorMessageOf(err))`.
  - Pass `onMoveService` and `onMoveRejected` (→ `setCollectionActionError`) through `ArchitectureDiagramPanel`, and through `PopoutCanvasDialog` as well.
  - The cross-region message is `"<service_code>" can only move to a box in <region>.` (contracts/ui.md §A).

**Checkpoint**: quickstart §2 steps 2–6 pass.

---

## Phase 8: User Story 3: Richer hover pop-up (Priority: P2)

**Goal**: 15 labeled attribute lines, no Operation line, and no duplicated values.

**Independent Test**: quickstart §3.

- [X] T031 [P] [US3] (write first) Update `frontend/tests/unit/servicePopup.test.ts`:
  - **Replace**: the DynamoDB example no longer has an `Operation:` line, and the operation-only omission test is updated.
  - **Add**:
    - an RDS attribute set gives `databaseEngine: MySQL` (and `deploymentOption: Multi-AZ`) lines in `POPUP_ATTRIBUTE_KEYS` order, after `UsageType`;
    - EC2 attributes with `memory: 8 GiB` give a `memory: 8 GiB` line, and the summary line doesn't contain `8 GiB`;
    - an empty value is omitted;
    - `POPUP_ATTRIBUTE_KEYS` equals the 15 keys in spec FR-009 order.

  Add to `frontend/tests/unit/skuDetail.test.ts`: `summarizeAttributes(attrs, { exclude: ["memory"] })` omits memory, and a call without options is unchanged.
- [X] T032 [US3] Implement the changes that make T031 pass:
  - In `frontend/src/lib/skuDetail.ts`: `summarizeAttributes(attributes, options?: { exclude?: readonly string[] })`.
  - In `frontend/src/lib/servicePopup.ts`: export `POPUP_ATTRIBUTE_KEYS`, remove the Operation line, add the labeled lines after `UsageType`, and use the exclude option for the summary.
  - Update the module comments (016 FR-009–FR-011).

---

## Phase 9: User Story 5: Admins see system status and problems (Priority: P2)

**Goal**:
- The icon-coverage analysis runs from the monitor.
- `GET /admin/system-info` is added.
- The Admin tab is restructured into User Management, then System Information with the Issues table.

**Independent Test**: quickstart §5 steps 1 and 4.

**Depends on**: US4 (`active_snapshot.py`).

### Tests (write first)

- [X] T033 [P] [US5] Create `backend/tests/unit/test_icon_coverage.py` for `find_unmatched_services(parquet_dir, snapshot_date, previous_date) -> list[Issue]` in `backend/src/pricing_data/icon_coverage.py`. Build a tmp tree (T003) whose `service_dim` has AmazonDynamoDB, AWSDataTransfer, ZZNewService and ZZOldService, and where the previous date has ZZOldService only. Then:
  - Only ZZNewService and ZZOldService are returned; DynamoDB is mapped and AWSDataTransfer is special.
  - ZZNewService has `is_new=True` and ZZOldService has `is_new=False`.
  - `service_name` comes from `service_dim`.
  - With `previous_date=None`, `is_new` is False for all.

  Add `previous_complete_or_present_date(parquet_dir, date)`, which returns the next-older date present in all five tables (markers not required) or `None`.
- [X] T034 [P] [US5] Create `backend/tests/unit/test_icon_map_consistency.py`. It asserts that `backend/src/pricing_data/aws_service_icons.json`'s `by_code`, `by_code_and_family` and `special_codes` equal the maps in `frontend/src/lib/awsServiceIcons.generated.ts`, parsed with a regex over the `key: "value"` lines of each exported object.
- [X] T035 [P] [US5] Create `backend/tests/contract/test_admin_system_info.py` covering contracts/api.md §1:
  - **(1)** An admin gets 200 with every field, and `active_snapshot_date` equals the active fixture date.
  - **(2)** A non-admin gets 403.
  - **(3)** After setting `STATE.issues` via a fixture, those issues come back in the documented order.

  Use the existing admin/auth fixtures from `test_admin_users.py`.

### Implementation

- [X] T036 [US5] Implement `backend/src/pricing_data/icon_coverage.py`:
  - Load `aws_service_icons.json` once.
  - Read `service_dim` for the date via DuckDB (`SELECT DISTINCT service_code, min(service_name)`).
  - Compute `is_new` against `previous_complete_or_present_date`.
  - Return the sorted `missing_icon` `Issue`s, each with a `message`.

  Wire it into `active_snapshot.run_check` as the analysis hook: it replaces the `missing_icon` issues and keeps the `missing_regions` and `pinned_incomplete` issues. This makes T033 pass.
- [X] T037 [US5] Add `SystemInfoOut`, `WaitingSnapshotOut` and `IssueOut` to `backend/src/models/schemas.py` per contracts/api.md §1. Create `backend/src/api/admin_system.py` with `GET /admin/system-info`, using `Depends(require_admin)` and mapping `STATE` into `SystemInfoOut` with the issue ordering from data-model.md §2. Register it in `backend/src/main.py`. This makes T035 pass. Then regenerate `frontend/src/api/generated/schema.d.ts`, and add `api.getSystemInfo()` and `export type SystemInfo` to `frontend/src/api/client.ts`.
- [X] T038 [US5] Create `frontend/src/components/admin/SystemInformationSection.tsx` per contracts/ui.md §E:
  - `useQuery(["systemInfo"], api.getSystemInfo, { refetchInterval: 60_000 })`;
  - the active date, with a "Pinned" badge;
  - the last check time via `toLocaleString()`;
  - the waiting list;
  - `last_check_error` in destructive text;
  - an Issues table (Type · Detail · Snapshot · New), with "No issues." when empty.

  Restructure `frontend/src/pages/AdminPage.tsx`: today's content under an `<h2>User Management</h2>` section, followed by `<SystemInformationSection />` under `<h2>System Information</h2>`.
- [X] T039 [P] [US5] Create `frontend/tests/unit/SystemInformationSection.test.tsx` with a mocked `api.getSystemInfo`:
  - the active date and Pinned badge render;
  - the waiting reason renders;
  - a `missing_icon` row shows its code and a New marker;
  - a `missing_regions` row lists its regions;
  - an empty issues list shows "No issues.".

---

## Phase 10: User Story 8: Operational settings are configurable (Priority: P3)

**Goal**: the remaining hard-coded operational values become settings, documented in one place.

**Independent Test**: quickstart §6.

- [X] T040 [US8] (write first) Extend `backend/tests/unit/test_settings.py`:
  - `cors_allowed_origins` defaults to `["http://localhost:5173"]`, and `CORS_ALLOWED_ORIGINS='["http://a","http://b"]'` parses to a list;
  - `catalog_search_default_limit` defaults to 50 and `catalog_search_max_limit` to 200, and a default above the max is rejected;
  - `password_hash_iterations` defaults to 260000, and 1000 is rejected;
  - `log_level` defaults to `INFO`, and `LOUD` is rejected;
  - `verify_password` accepts a hash made with 260000 iterations after the setting changes to 300000, i.e. the stored count is honored.
- [X] T041 [US8] Add the fields from T040 to `Settings` in `backend/src/config.py`, with validators (`Field(ge=...)`, `Literal[...]` for the log level, and a `model_validator` for default ≤ max). Then wire them in:
  - `backend/src/main.py`: `allow_origins=settings.cors_allowed_origins`, and `logging.basicConfig(level=settings.log_level)`;
  - `backend/src/api/catalog.py`: the default and clamp use the settings;
  - `backend/src/services/auth_service.py`: `hash_password` uses `settings.password_hash_iterations`, and the `_ITERATIONS` constant is removed.

  This makes T040 pass.
- [X] T042 [P] [US8] Create `docs/configuration.md`: a table of every `Settings` field (data-model.md §7) with its env var, type, default and meaning, plus a note that invalid values stop startup. Create `backend/.env.example` listing every variable commented out, with its default. Link both from `backend/README.md`.

---

## Phase 11: Polish & Cross-Cutting Concerns

- [X] T043 [P] Check that the 015 comments still hold in `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx` and `frontend/src/lib/servicePopup.ts`: update any that describe the flex-wrap icon row, `pb-3`, the 24px size, or the Operation line.
- [X] T044 Run the full gates and fix any failures:
  - `cd backend && uv run pytest && uv run ruff check src tests scripts/generate_aws_service_icon_map.py scripts/build_test_pricing_fixture.py`
  - `AWS_PRICING_PARQUET_DIR=tests/fixtures/pricing_parquet uv run pytest`, which mirrors CI
  - `cd frontend && npm run check-api-types && npm run lint && npm test && npm run build`
- [X] T045 Run the manual quickstart.md §2–§6 against this repo's frontend and backend, as Admin, including the scratch-copy snapshot walkthrough in §5. Record any deviations as notes in `specs/016-canvas-icon-layout/quickstart.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001–T002)**: no dependencies. T001 is needed before CI can pass once US4 lands. T002 is needed by US5.
- **Foundational (T003–T005)**: T003 blocks the US4 and US5 backend tests. T005 blocks US4 (T017).
- **US1**: independent. **US2** depends on US1 (T007–T009).
- **US4**: depends on the Foundational phase. **US5** depends on US4 (T014) and T002.
- **US6**: independent. It shares `WorkspacePage.tsx` with T030, so do T019 before T030.
- **US7**: independent. It shares `ArchitectureDiagramPanel.tsx` with US1 and US2, so do it after T009 and before T029, to avoid conflicts.
- **US3**: independent (lib files only).
- **US8**: independent, but touches `main.py` and `config.py` after US4's T017 and T005.
- **Polish**: last.

### Same-file sequencing

- `ArchitectureDiagramPanel.tsx`: T008 → T009 → T023 → T029
- `WorkspacePage.tsx`: T019 → T030
- `config.py`: T005 → T041
- `main.py`: T017 → T037 → T041
- `schemas.py`: T027 → T037
- `schema.d.ts` regeneration: after T027, and again after T037

### Parallel Opportunities

- T001 and T002.
- All the "write first" test tasks within a phase: T011, T012 and T013; T024, T025 and T026; T033, T034 and T035.
- The backend track (US4 → US5, then US8) alongside the frontend track (US1 → US7 → US2, US3, US6).
- T031/T032 (US3) at any time.

---

## Parallel Example: two tracks

```bash
# Backend track
Task: "T003 parquet_tree helper"  →  "T011–T013 active snapshot tests"  →  "T014–T018 active snapshot"
Task: "T033–T035 coverage/system-info tests"  →  "T036–T037"

# Frontend track (in parallel)
Task: "T006 iconLayout tests"  →  "T007–T010 icons 60px/spacing"
Task: "T021 newNodePlacement tests"  →  "T022–T023"
Task: "T031 pop-up tests"  →  "T032"
```

---

## Implementation Strategy

### MVP

**US1 + US4**: the most visible change, together with the pricing-correctness safeguard. US6 and US7 are small P1 defect fixes that can ship alongside them.

### Incremental Delivery

1. Setup + Foundational.
2. US4 (active snapshot): validate quickstart §5 steps 2–3 and 5–6.
3. US1 (icons): quickstart §2 step 1.
4. US6 + US7 (defects): quickstart §4.
5. US3 (pop-up): quickstart §3.
6. US2 (drag and move): quickstart §2 steps 2–6.
7. US5 (Admin System Information): quickstart §5 steps 1 and 4.
8. US8 (configuration): quickstart §6.
9. Polish.

---

## Notes

- Generated files (`awsServiceIcons.generated.ts`, `aws_service_icons.json`, `schema.d.ts` and the fixture) change only by re-running their generators.
- No Postgres migration and no new dependency are expected. If either seems necessary, stop and revisit plan.md › Constitution Check.
- The real pricing data already has `_SUCCESS` for 2026-09-24. Don't modify it; quickstart §5 uses a scratch copy.
