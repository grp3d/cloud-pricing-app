---

description: "Task list for 015-canvas-service-icons"
---

# Tasks: Canvas Service Icons & Per-Architecture Pricing Results

**Input**: Design documents from `specs/015-canvas-service-icons/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, contracts/ui.md, quickstart.md

**Tests**: Included, and written **first** where Principle V requires it: the DuckDB query change,
contract tests, and pure logic that transforms prices or user-defined relationships (pricing-result
store, priced-contents equality, request-context capture). The icon resolver and pop-up line
builder are also test-first, because they pin FR-003 and FR-008. Every test task marked
"(write first)" MUST be seen failing before its implementation task. Presentational component
tests may follow implementation.

**Organization**: Tasks are grouped by user story so each can be built and tested on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**:
  - US1 = canvas icons (P1)
  - US2 = hover pop-up (P1)
  - US3 = zoom scaling (P2)
  - US4 = per-architecture pricing (P1)
  - US5 = word-wrap toggle placement (P3)
- Paths are relative to the repository root (`backend/`, `frontend/`)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Generate the static icon assets and mapping that US1–US3 render.

- [ ] T001 Create `backend/scripts/generate_aws_service_icon_map.py` per research.md §1 and §4.
  - **CLI**: `--icons <aws_architecture_icons dir>` and `--parquet <pricing parquet dir>`, defaulting to `Settings().aws_pricing_parquet_dir`.
  - **Service codes**: read distinct `service_code`, with `service_name` from `service_dim` and the `(service_code, product_family)` pairs from `product_dim`, via DuckDB across all regions for the latest snapshot.
  - **Icons**: collect every `Architecture-Service-Icons_*/*/48/Arch_*_48.svg`, using the stem between `Arch_` and `_48`.
  - **Normalization**: lowercase, strip a leading `amazon`/`aws`, and drop non-alphanumerics.
  - **Match order**: exact match on the normalized service code, then exact on the normalized service name, then `difflib.get_close_matches(cutoff=0.8)` on the service name.
  - **Overrides**: a checked-in `OVERRIDES: dict[str, str]` holding every service-code override listed in research.md §1 (e.g. `AmazonEKS → Amazon-Elastic-Kubernetes-Service`, `AWSOutposts → AWS-Outposts-family`). It always beats the automatic match.
  - **Family overrides**: a checked-in `FAMILY_OVERRIDES: dict[str, dict[str, str]]` holding every product-family override in research.md §1: EC2 storage families → `Amazon-Elastic-Block-Store`, EC2 `NAT Gateway` → `Amazon-Virtual-Private-Cloud`, EC2 load-balancer families → `Elastic-Load-Balancing`, VPC `VpcEndpoint` → `AWS-PrivateLink`, RDS `Aurora Global Database` → `Amazon-Aurora`.
  - **Special icons**: `AWSDataTransfer` is not mapped by code; it uses the data-transfer icon.
- [ ] T002 Extend `backend/scripts/generate_aws_service_icon_map.py` to write its outputs deterministically (sorted keys, stable formatting, so running twice is byte-identical):
  - **(a)** `frontend/src/lib/awsServiceIcons.generated.ts`, a header comment saying "generated, do not edit" followed by these exports (shapes in data-model.md §2):
    - `AWS_SERVICE_ICON_BY_CODE`
    - `AWS_SERVICE_ICON_BY_CODE_AND_FAMILY`
    - `AWS_FALLBACK_ICON = { light: "AWS-Cloud-logo", dark: "AWS-Cloud-logo_Dark" }`
    - `AWS_DATA_TRANSFER_ICON = { light: "Data-Stream_Light", dark: "Data-Stream_Dark" }`
  - **(b)** Clear `frontend/src/assets/aws-icons/`, then copy in:
    - every referenced service SVG as `<stem>.svg`;
    - `Architecture-Group-Icons_*/AWS-Cloud-logo_32.svg` → `AWS-Cloud-logo.svg`;
    - `AWS-Cloud-logo_32_Dark.svg` → `AWS-Cloud-logo_Dark.svg`;
    - `Resource-Icons_*/Res_General-Icons/Res_48_Light/Res_Data-Stream_48_Light.svg` → `Data-Stream_Light.svg`;
    - the matching `Res_48_Dark` file → `Data-Stream_Dark.svg`.
  - **(c)** Print a report with matched, overridden and fallback sections, and the non-fallback percentage.
- [ ] T003 Run `cd backend && uv run python scripts/generate_aws_service_icon_map.py --icons ../../images-web/aws_architecture_icons` and review the report:
  - Confirm at least 90% non-fallback (SC-002).
  - Confirm every service code in `backend/src/db/seed/standard_architectures.json` resolves to a non-fallback icon.
  - If either check fails, add overrides to the script and re-run.
  - Commit the generated `frontend/src/lib/awsServiceIcons.generated.ts` and `frontend/src/assets/aws-icons/*.svg`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Deliver the `SKUSelectionOut.product_family` API field (contracts/api.md). US1 needs
it to pick product-family icons. US4 does not depend on this phase and may start in parallel.

**⚠️ CRITICAL**: US1–US3 cannot be completed until this phase is done.

### Tests (write first, confirm they fail)

- [ ] T004 [P] Add failing tests to `backend/tests/unit/test_catalog.py` for a new `resolve_product_details(skus, *, region, snapshot_date=None) -> dict[tuple[str, str], ProductDetails]` in `backend/src/pricing_data/catalog.py`, where `ProductDetails` is a frozen dataclass with `attributes: dict[str, str]` and `product_family: str | None`:
  - The fixture NAT Gateway SKU `("AmazonEC2", "2QF2GD6XUCJHFMKF")` in `us-west-2` returns `product_family == "NAT Gateway"` and non-empty attributes containing `usagetype`.
  - A SKU with an empty `product_family` returns `None`.
  - A missing SKU is absent from the dict.
  - An `AWSDataTransfer` SKU is scoped by `fromRegionCode`, the same as `resolve_attributes`.
  - An empty input returns `{}` without querying.
  - `resolve_attributes` still returns the same values as before (regression).
  - Adjust the SKU and region to what `backend/tests/fixtures/pricing_parquet` actually contains.
- [ ] T005 [P] Add failing contract tests to `backend/tests/contract/test_architectures.py`:
  - `GET /architectures/{id}` returns `product_family` on every `collections[].sku_selections[]` item and on `connectors[].sku_selection`.
  - It is `"NAT Gateway"` for the fixture NAT Gateway SKU.
  - It is `null` for a SKU missing from the snapshot, with `attributes == {}` unchanged.
- [ ] T006 [P] Add failing contract tests to `backend/tests/contract/test_sku_selections.py`: the create (`POST`) and update (`PATCH /sku-selections/{id}`) responses include `product_family`. Add the same assertion for the connector SKU-selection attach response in `backend/tests/contract/test_connector_sku_selection.py`.

### Implementation

- [ ] T007 Implement `ProductDetails` and `resolve_product_details` in `backend/src/pricing_data/catalog.py`:
  - Reuse `resolve_attributes`' query, adding `product_family` to the `SELECT` while keeping the same region-scoping `WHERE` and the same error handling.
  - Normalize `""` to `None`.
  - Reimplement `resolve_attributes` as a thin wrapper returning `{k: v.attributes}`, so existing callers are unchanged.
  - Makes T004 pass.
- [ ] T008 Add `product_family: str | None = None` to `SKUSelectionOut` in `backend/src/models/schemas.py`, with a comment that it is resolved read-only from Parquet at response time and never stored (015, contracts/api.md).
- [ ] T009 Switch `backend/src/services/architecture_service.py` to `resolve_product_details`, attaching both `attributes` and `product_family`:
  - Change `_region_grouped_batch_resolve` to return `(units, details)`. It is still one details query per distinct region.
  - Update `attach_units_to_architecture._attach` and `sku_selection_out_with_unit` to match.
  - Makes T005 and T006 pass.
- [ ] T010 Regenerate the frontend API types. With the backend running, run `cd frontend && npm run generate-api-types`, then confirm `frontend/src/api/generated/schema.d.ts` contains `product_family?: string | null` on `SKUSelectionOut` and that `npm run check-api-types` is clean.

**Checkpoint**: `cd backend && uv run pytest` is green, and `product_family` is visible in the architecture detail response.

---

## Phase 3: User Story 1: See services as AWS icons on the canvas (Priority: P1) 🎯 MVP

**Goal**: Each SKU selection inside an Application Component or VPC box renders as its AWS icon
(or the fallback) instead of a text row, and stays clickable to select the service.

**Independent Test**: Open "Serverless Microservices Back-End". Each service shows a recognizable
icon, Lambda's appears twice, no `service_code / sku` text rows remain, and clicking an icon opens
its configuration in column 3 (quickstart §3).

### Tests (write first, confirm they fail)

- [ ] T011 [P] [US1] Create `frontend/tests/unit/awsServiceIcons.test.ts` for `resolveAwsServiceIcon(serviceCode, productFamily)` from `frontend/src/lib/awsServiceIcons.ts`:
  - `("AmazonDynamoDB", null)` resolves to a URL containing `Amazon-DynamoDB` with `isFallback === false`.
  - `("AmazonEC2", "NAT Gateway")` resolves to `Amazon-Virtual-Private-Cloud`: the family override wins.
  - `("AmazonEC2", "Compute Instance")` resolves to `Amazon-EC2`.
  - `("AWSDataTransfer", "Data Transfer")` gives distinct light and dark `Data-Stream` URLs.
  - `("NotARealService", null)` returns the fallback with `isFallback === true` and distinct light and dark URLs.
  - Repeated calls return identical results.
  - **Integrity check**: every stem referenced in `awsServiceIcons.generated.ts`, including the fallback and data-transfer stems, has a matching file in `frontend/src/assets/aws-icons/`. Check this via `import.meta.glob` keys.

### Implementation

- [ ] T012 [US1] Implement `frontend/src/lib/awsServiceIcons.ts`:
  - Load `import.meta.glob("../assets/aws-icons/*.svg", { eager: true, query: "?url", import: "default" })`.
  - Build a stem → URL map.
  - Export `interface ResolvedServiceIcon { lightUrl: string; darkUrl: string; isFallback: boolean }` and `resolveAwsServiceIcon(serviceCode: string, productFamily: string | null | undefined): ResolvedServiceIcon`, following the resolution order in data-model.md §2.
  - Add a module doc comment in the style of `awsDataTransfer.ts`.
  - Makes T011 pass.
- [ ] T013 [US1] In `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`, replace `ServiceList`'s `<ul>` of text buttons with a `flex flex-wrap gap-1` container holding one `ServiceIconButton` per SKU selection, in the same order:
  - `<button type="button">` 24×24 px with `aria-pressed={s.id === selectedServiceId}`.
  - A selected state shown as a visible ring (e.g. `ring-2 ring-primary`), replacing the underline.
  - The same `onClick` with `stopPropagation()` → `onSelectService(s.id)`.
  - Inside: `<img alt="" draggable={false}>` using `resolveAwsServiceIcon(s.service_code, s.product_family)`. When `lightUrl !== darkUrl`, render two imgs with `dark:hidden` / `hidden dark:block`.
  - A temporary `aria-label` of `` `${s.service_code} ${s.sku}` ``; T017 replaces it with the pop-up text.
  - Leave the "No services yet." / `hideEmptyMessage` branch and all box, VPC and connector labels unchanged (FR-007).
  - Remove the now-unused `summarizeAttributes` import only if nothing else in the file uses it.
- [ ] T014 [P] [US1] Create `frontend/tests/unit/ServiceIconList.test.tsx`. Render `ServiceList`, exporting it from `ArchitectureDiagramPanel.tsx` if needed, as a named export for testing. Assert:
  - One button per selection, each containing an img, with two DynamoDB selections giving two buttons.
  - No text matching `/ \/ /` is rendered.
  - Clicking a button calls `onSelectService` with that id.
  - The selected id's button has `aria-pressed="true"`.
  - An empty list renders "No services yet." unless `hideEmptyMessage`.
  - Render `ServiceList` inside a `ReactFlowProvider` in every test case, so the tests keep passing once T019 adds `useStore` to the icon and pop-up subtree.

**Checkpoint**: US1 is fully functional. Icons show on the canvas, and clicking selects the service.

---

## Phase 4: User Story 2: Hover an icon to see the service details (Priority: P1)

**Goal**: Hovering or focusing an icon shows the labeled, line-per-field pop-up (FR-008 to
FR-012), and the icon's accessible name matches it.

**Independent Test**: Hover the DynamoDB PayPerRequest read icon and see exactly the spec's
five-line example. A PITR SKU shows no `Operation:` line. Tabbing to an icon shows the same
pop-up (quickstart §4).

### Tests (write first, confirm they fail)

- [ ] T015 [P] [US2] Create `frontend/tests/unit/servicePopup.test.ts` for `buildServicePopupLines(selection)` from `frontend/src/lib/servicePopup.ts`:
  - **(a)** Service code `AmazonDynamoDB`, SKU `3ERQSZWPAMX2JWHN`, attributes `{ groupDescription: "DynamoDB PayPerRequest Read Request Units", usagetype: "EU-ReadRequestUnits", operation: "PayPerRequestThroughput" }` returns exactly `["AmazonDynamoDB", "Sku: 3ERQSZWPAMX2JWHN", "DynamoDB PayPerRequest Read Request Units", "UsageType: EU-ReadRequestUnits", "Operation: PayPerRequestThroughput"]`.
  - **(b)** `operation: ""` omits the Operation line; a missing `usagetype` omits the UsageType line.
  - **(c)** EC2 attributes with `instanceType`/`memory`/`vcpu` produce a summary line equal to `summarizeAttributes(attributes)`.
  - **(d)** No summary keys means no summary line.
  - **(e)** An `AWSDataTransfer` selection with from/to region attributes: line 2 is `Sku: <real sku>` and line 3 is `awsDataTransferLabel(...)`.
  - **(f)** No line is ever empty or ends in `": "`.

### Implementation

- [ ] T016 [US2] Implement `frontend/src/lib/servicePopup.ts`:
  - `buildServicePopupLines(selection: Pick<SkuSelection, "service_code" | "sku" | "attributes">): string[]`, following data-model.md §3 and reusing `summarizeAttributes` (`lib/skuDetail.ts`) and `awsDataTransferLabel` (`lib/awsDataTransfer.ts`).
  - `servicePopupAccessibleName(lines: string[]): string`, returning `lines.join(", ")`.
  - Makes T015 pass.
- [ ] T017 [US2] In `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`, wrap each `ServiceIconButton` in the existing shadcn `Tooltip` / `TooltipTrigger asChild` / `TooltipContent` (from `../ui/tooltip`):
  - The content renders one `<div>` per line from `buildServicePopupLines(s)`, with no empty lines.
  - Set the button's `aria-label` to `servicePopupAccessibleName(lines)` (FR-012).
  - Keep the Radix default open-on-hover and open-on-focus behavior and close on leave, blur or Escape (FR-011).
  - Make sure `TooltipProvider` is present above the canvas. Reuse the app's existing provider if one wraps the workspace; otherwise add one around the diagram.
- [ ] T018 [P] [US2] Extend `frontend/tests/unit/ServiceIconList.test.tsx`: the button's accessible name equals the joined pop-up lines, and focusing the button shows tooltip content containing `Sku: <sku>` and `UsageType: …` on separate elements.

**Checkpoint**: US1 and US2 together fully replace the old text rows with no loss of information.

---

## Phase 5: User Story 3: Icons and pop-ups scale with canvas zoom (Priority: P2)

**Goal**: Icon size and pop-up text scale with the zoom controls, in both the in-column and
pop-out canvases (FR-013, FR-014).

**Independent Test**: Zoom in twice and out four times. Icons track box label size, and a hovered
pop-up's text scales to match. The pop-out canvas behaves the same (quickstart §5).

### Implementation

- [ ] T019 [US3] In `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`, read the live zoom inside the service-icon subtree with `useStore((s) => s.transform[2])` from `@xyflow/react`, which works inside custom nodes under the panel's `ReactFlowProvider`. Apply it to the `TooltipContent` inner wrapper:
  - `style={{ fontSize: \`calc(var(--text-2xs) * ${zoom})\` }}`.
  - Padding and line gap in `em` units (e.g. `px-[0.6em] py-[0.4em]`, `gap-[0.2em]`) instead of fixed px classes.
  - Do **not** use `transform: scale` (research.md §5).
  - Icons themselves need no change, because they scale through the viewport transform. Confirm the 24px size isn't counter-scaled anywhere.
- [ ] T020 [US3] Manually verify quickstart §5 in the dev server:
  - The in-column canvas follows the +/−, scroll-zoom and fit-view controls.
  - `PopoutCanvasDialog` behaves the same.
  - Node heights grow correctly as icons wrap (measured-height path).
  - Fix any clipping or overflow found in `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`.

**Checkpoint**: US1–US3 are complete. The canvas feature is shippable on its own.

---

## Phase 6: User Story 4: Pricing column shows the active architecture's own result (Priority: P1)

**Goal**: Column 5 always shows the active architecture's stored result:
- The result is persisted per architecture in `localStorage`.
- It is auto-calculated when absent.
- Duration is restored per architecture.
- Errors are per architecture.
- Late results are stored against the right architecture.
- An "Architecture has been updated since last pricing" notice appears when priced contents diverge (FR-015 to FR-022, FR-018a/b).

**Independent Test**: Run quickstart §6 end-to-end: calculate A, auto-calculate B, switch back to
A with no request and the duration restored, reload and keep A, the stale notice appears and
clears, the switch race, no auto-calculation for empty architectures, and delete cleanup.

**Note**: US4 does not depend on Phase 1 or Phase 2 and can be built in parallel with US1–US3.

### Tests (write first, confirm they fail)

- [ ] T021 [P] [US4] Add failing tests to `frontend/tests/unit/priceChange.test.ts` for `PricedContentsEntry` and `pricedContentsEqual(a, b)` in `frontend/src/lib/priceChange.ts`:
  - Equal regardless of order.
  - Not equal when any one field differs: `usage_quantity`, `pricing_term`, `purchase_option`, `sku`, `service_code` or `region`.
  - Not equal when lengths differ.
  - Handles duplicate entries as a multiset: two identical entries vs one is not equal.
  - `decideBaselineUpdate`'s existing cases stay green.
- [ ] T022 [P] [US4] Create `frontend/tests/unit/architecturePricingResults.test.ts` for `readPricingResult`, `writePricingResult` and `removePricingResult` in `frontend/src/lib/architecturePricingResults.ts`:
  - A write/read round-trip under key `cloud-pricing-result-<id>` returns the same entry.
  - Entries for two architectures are independent.
  - A missing key returns `null`.
  - Malformed JSON returns `null`.
  - A wrong shape (e.g. `version: 2`, or missing `result`/`duration`/`pricedContents`) returns `null`.
  - `remove` deletes only that key.
  - `localStorage.getItem`/`setItem` throwing (stubbed) never throws out of read or write.
- [ ] T023 [P] [US4] Add failing tests for a pure helper `shouldAutoCalculate({ architectureId, hasSelections, hasStoredEntry, isInFlight })` exported from `frontend/src/lib/architecturePricingResults.ts`, in the same test file as T022. It returns `true` only when there is an id, it has selections, there is no stored entry and nothing is in flight.

- [ ] T024 [P] [US4] Add failing tests to `frontend/tests/unit/architecturePricingResults.test.ts` for a pure `applyCalculationSuccess({ entries, vars, result, decision, comparisonTotal, previousEntry, now })` → `{ entries, entry, newBaseline }` in `frontend/src/lib/architecturePricingResults.ts`. Here `vars = { architectureId, duration, pricedContents, priceChangeSelections, prior }` is the request context captured at call time. Cases:
  - **(a)** A result for A applied while `entries` holds B: only A's entry is added or replaced, and B's entry is unchanged (FR-020, FR-016).
  - **(b)** `decision: "establish"`: `entry.priceChange === null`, and `newBaseline` = {result total, `vars.duration`, `vars.priceChangeSelections`}.
  - **(c)** `"direct"` / `"duration_adjusted"` / `"duration_only"`: `entry.priceChange === String(total − comparisonTotal)`, and `newBaseline` is set.
  - **(d)** `"unchanged"`: `entry.priceChange === previousEntry?.priceChange ?? null`, and `newBaseline === null` (baseline untouched) (FR-022).
  - **(e)** `entry.duration` and `entry.pricedContents` come from `vars`, never from anything current (FR-020).

### Implementation

- [ ] T025 [US4] In `frontend/src/lib/priceChange.ts`:
  - Add `export interface PricedContentsEntry extends PriceChangeSelection { region: string | null }`.
  - Generalize the existing private multiset comparison to take a key function.
  - Export `pricedContentsEqual(a: PricedContentsEntry[], b: PricedContentsEntry[]): boolean`, whose key includes `region`.
  - Keep `selectionsEqual`'s behavior identical.
  - Makes T021 pass.
- [ ] T026 [US4] Create `frontend/src/lib/architecturePricingResults.ts`, mirroring `lib/priorCalculation.ts`'s `localStorage` + try/catch + type-guard pattern. Export:
  - `PricingResultEntry` (data-model.md §5: `version: 1`, `result`, `duration`, `priceChange`, `pricedContents`, `calculatedAt`), with `result` typed as `Awaited<ReturnType<typeof api.calculate>>`.
  - `readPricingResult`, `writePricingResult`, `removePricingResult` and `shouldAutoCalculate`.
  - Also export `applyCalculationSuccess`. It is pure and does no I/O; persistence stays with the caller.
  - Makes T022, T023 and T024 pass.
- [ ] T027 [US4] In `frontend/src/pages/WorkspacePage.tsx`, add a `currentPricedContents` memo next to `currentPriceChangeSelections`. It has the same fields plus `region`: the owning Collection's region for Collection selections, and the Connector's `from` Collection's region for Connector selections. Extend the existing `skuSelectionsById` construction if it doesn't already carry the owner.
- [ ] T028 [US4] Refactor the calculate flow in `frontend/src/pages/WorkspacePage.tsx`:
  - **State**: replace the single `calculation` / `calculationError` / `priceChange` state with:
    - `resultEntries: Map<string, PricingResultEntry>`, lazily hydrated from `readPricingResult` for the active id;
    - `calculationErrors: Map<string, string>`, in memory;
    - `inFlight: Set<string>`, held in a ref plus state for re-render.
  - **Mutation variables**: change `useMutation` to take `{ architectureId, duration, pricedContents, priceChangeSelections, prior }`, captured at call time. The `onMutate`, `onSuccess` and `onError` handlers use **only** these variables, never the closure (FR-020, research.md §6).
  - **Price change**: in `onSuccess(result, vars)`:
    1. Compute `decision = decideBaselineUpdate({ prior: vars.prior, currentSelections: vars.priceChangeSelections, newDuration: vars.duration })`.
    2. For `"duration_adjusted"` and `"duration_only"`, fetch `comparisonTotal` with `api.calculateSnapshot(vars.duration, vars.prior!.selections)`. For `"direct"`, use `vars.prior!.total`. Otherwise it is `null`.
    3. Call `applyCalculationSuccess(...)` with `previousEntry = resultEntries.get(vars.architectureId)`, then update `resultEntries`.
    4. Persist: call `writePricingResult(vars.architectureId, entry)` always, and `writePriorCalculation(vars.architectureId, newBaseline)` only when `newBaseline !== null`.
    - Never read `architectureId`, `priorCalculation` or `currentPriceChangeSelections` from the closure.
  - **Errors**: in `onError`, set `calculationErrors[architectureId]`.
  - **Calculate / Retry**: the button and retry build the variables from the active architecture's current values.
- [ ] T029 [US4] In `frontend/src/pages/WorkspacePage.tsx`, add architecture-switch behavior:
  - **Duration sync**: when `architectureId` changes, if a stored entry exists, `setCalculationDuration(entry.duration)` (FR-018b); otherwise leave the duration unchanged.
  - **Auto-calculation**: a `useEffect` keyed on `architectureId` and the architecture query's loaded data. It fires the calculate mutation once when `shouldAutoCalculate(...)` is true, using the current dropdown duration (FR-017). It never fires for an architecture with no SKU selections.
- [ ] T030 [US4] In `frontend/src/pages/WorkspacePage.tsx`, pass `PricingPanel` only the active architecture's values:
  - `calculation={entry?.result ?? null}`, `priceChange={entry?.priceChange ?? null}` and `calculationError={calculationErrors.get(activeId) ?? null}`.
  - `isCalculating={inFlight.has(activeId)}`.
  - A new `isOutOfDate={entry != null && !pricedContentsEqual(entry.pricedContents, currentPricedContents)}` prop (FR-016, FR-018a).
  - Add `frontend/tests/unit/WorkspacePage.pricing.test.tsx`. It renders `WorkspacePage` with a mocked `api` and a pre-seeded `cloud-pricing-result-<id>` entry, then asserts that `api.calculate` is never called and the stored total is displayed (FR-018, SC-006).
- [ ] T031 [US4] In `frontend/src/pages/WorkspacePage.tsx`, extend `deleteArchitecture`'s `onSuccess` to call `removePricingResult(id)` and drop `id` from `resultEntries` and `calculationErrors`.
- [ ] T032 [US4] In `frontend/src/components/workspace/PricingPanel.tsx`, add the `isOutOfDate: boolean` prop. When true, render `<p role="status" className="flex items-center gap-1.5 text-2xs text-amber-700 dark:text-amber-500"><AlertTriangle className="size-4 shrink-0" /> Architecture has been updated since last pricing</p>` **directly below** the `Data Timestamp:` line (contracts/ui.md §C).
- [ ] T033 [P] [US4] Create or extend `frontend/tests/unit/PricingPanel.test.tsx`:
  - With `isOutOfDate` true, the notice text is present and is the next sibling after the Data Timestamp line.
  - With `isOutOfDate` false, it is absent.

**Checkpoint**: Quickstart §6 passes. Switching never shows another architecture's price.

---

## Phase 7: User Story 5: Word-wrap toggle sits next to the Price per Sku heading (Priority: P3)

**Goal**: Move the Price per Sku word-wrap toggle from the bottom of column 5 to the heading row,
right-aligned with the prices (FR-023).

**Independent Test**: On any calculated result, the toggle is on the "Price per Sku" heading row,
right-aligned, and works as before. Nothing but Data Timestamp (and the notice) sits below the
list. At minimum column width the heading truncates rather than overlapping (quickstart §7).

### Implementation

- [ ] T034 [US5] In `frontend/src/components/workspace/PricingPanel.tsx`:
  - Pass `onToggleWordWrap` into `PricePerSkuSection` (alongside the existing `wordWrap`).
  - Change its `<h4>Price per Sku</h4>` into a `flex items-center justify-between gap-2` row: `<h4 className="min-w-0 truncate text-2xs font-semibold">Price per Sku</h4>` followed by the existing word-wrap `Tooltip`/`Button`, moved as-is with the same `aria-label`, `aria-pressed`, tooltip text and `WrapText` icon, and `className="shrink-0"` replacing `self-start`.
  - Delete the old toggle block after the Data Timestamp line and update its explanatory comment.
- [ ] T035 [P] [US5] Extend `frontend/tests/unit/PricingPanel.test.tsx`:
  - The button named "Enable word wrap for Price per Sku" is inside the same row element as the "Price per Sku" heading.
  - No toggle is rendered after the Data Timestamp line.
  - Clicking it flips `aria-pressed`.

**Checkpoint**: All five stories are complete.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T036 [P] Update the spec comment trail in the touched files, in the house style (`015-canvas-service-icons, FR-0xx:` comments explaining *why*):
  - `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx`
  - `frontend/src/components/workspace/PricingPanel.tsx`
  - `frontend/src/pages/WorkspacePage.tsx`
- [ ] T037 Run the full gates:
  - `cd backend && uv run pytest`
  - `cd frontend && npm run check-api-types && npm run lint && npm test && npm run build`
  - Fix any failures.
- [ ] T038 Run the manual quickstart.md §3–§7 in the dev server, covering light and dark themes, and record any deviations as follow-up notes in `specs/015-canvas-service-icons/quickstart.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies. It needs the local icon package and Parquet data. Its outputs are committed, so later phases and CI don't need them.
- **Foundational (Phase 2)**: Independent of Phase 1. Blocks US1's product-family icons (T013 reads `s.product_family`, typed after T010).
- **US1 (Phase 3)**: Depends on Phase 1 (assets and map) and Phase 2 (T010 types).
- **US2 (Phase 4)**: Depends on US1 (T013's `ServiceIconButton`).
- **US3 (Phase 5)**: Depends on US2 (T017's `TooltipContent`).
- **US4 (Phase 6)**: Independent of Phases 1–5 and can start immediately.
- **US5 (Phase 7)**: Independent. It shares `PricingPanel.tsx` with T032, so sequence T032 and T034 to avoid edit conflicts.
- **Polish (Phase 8)**: After all desired stories.

### Within Each Story

- Tests marked "write first" come before implementation and must fail first.
- Lib modules (`awsServiceIcons.ts`, `servicePopup.ts`, `architecturePricingResults.ts`, `priceChange.ts`) come before the components and pages that use them.
- In US4, the `WorkspacePage.tsx` tasks T027 → T028 → T029 → T030 → T031 are sequential (same file).

### Parallel Opportunities

- T004, T005 and T006 (backend tests in different files).
- T011, T015, T021, T022, T023 and T024 (independent frontend lib tests) can all be written together.
- The US4 track (T021–T033) can run in parallel with the Phase 1 → US1 → US2 → US3 track.
- T014, T018, T033 and T035 are component tests in separate files or sections once their implementations exist.

---

## Parallel Example: US4 kickoff alongside the canvas track

```bash
# Developer A (canvas track):
Task: "T001–T003 generate icon map + assets"
Task: "T004 [P] resolve_product_details tests in backend/tests/unit/test_catalog.py"

# Developer B (pricing track), at the same time:
Task: "T021 [P] [US4] pricedContentsEqual tests in frontend/tests/unit/priceChange.test.ts"
Task: "T022 [P] [US4] pricing-result store tests in frontend/tests/unit/architecturePricingResults.test.ts"
Task: "T023 [P] [US4] shouldAutoCalculate tests in frontend/tests/unit/architecturePricingResults.test.ts"
```

---

## Implementation Strategy

### MVP First

The spec has three P1 stories. The recommended first increment is **US4**: it fixes a
correctness defect in a pricing tool (showing another architecture's price), has no dependency on
assets or the backend, and ships on its own.

The second increment is **US1 + US2** together. Icons without the pop-up would hide SKU details
users rely on today, so US1 should not ship alone.

### Incremental Delivery

1. US4 (T021–T033) → validate quickstart §6 → shippable fix.
2. Phase 1 + Phase 2 → US1 → US2 → validate quickstart §3–§4 → shippable canvas icons.
3. US3 → validate quickstart §5.
4. US5 → validate quickstart §7.
5. Polish (T036–T038).

---

## Notes

- [P] tasks touch different files and have no incomplete dependencies.
- Generated files (`awsServiceIcons.generated.ts`, `assets/aws-icons/*.svg`, `schema.d.ts`) are only ever changed by re-running their generators, never edited by hand.
- No Postgres migration and no new npm or Python dependency are expected. If one seems necessary, stop and revisit plan.md › Constitution Check.
