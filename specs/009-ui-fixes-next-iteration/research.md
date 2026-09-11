# Research: UI Fixes and Enhancements — Next Iteration

Phase 0 output. Each section resolves one area of the spec against the actual codebase (all
findings below were verified directly against the running source — the backend against the
live local Parquet dataset via DuckDB, the frontend against the current component tree — not
inferred from documentation).

## §1. SKU `2AB37QDFJZBGQ5YP` pricing failure (US1, FR-001)

**Decision**: No calculation-engine change is needed on its own. Direct reproduction of
`calculate_architecture_price()` against the live snapshot (`2026-09-11`) for this SKU across
all seven `pricing_term`/`purchase_option` combinations (on-demand plus all six Reserved
variants) returns a real, non-zero total with **zero exceptions and zero unpriceable
line items** in every case. The calculation engine is not the source of the reported failure.

**What the investigation did find**: this SKU's `price_fact` rows contain a genuine upstream
data anomaly — every Reserved term/purchase_option combination has **two rows with two
different prices** (e.g. `reserved_1yr`/`partial_upfront` has `Hrs` rows priced at both 1.868
and 1.715, and `Quantity` upfront-fee rows at both 16367.000 and 15025.000), where a normal SKU
has exactly one row per combination. This is present identically across every available
snapshot back to `2026-08-31` (not a transient ingestion glitch on one day). `lookup_reserved_price`
already has "first row wins" semantics for this exact situation (inherited from 006's fix for a
different, narrower duplicate case) — it doesn't crash, but it does mean the Reserved price this
SKU shows is **non-deterministic across ingestion runs** (whichever of the two rows DuckDB's
unordered scan happens to read first), which is a real correctness concern even though it isn't
a hard failure.

Since direct backend reproduction rules out the calculation engine, the actual user-visible
failure most plausibly originates in the add-to-architecture / catalog-search / frontend
price-rendering path, which this investigation could not reproduce without a live browser
session. **Implementation MUST start US1 with a live `claude-in-chrome` reproduction** — add
this exact SKU via the real search → select → configure → calculate flow — before writing any
fix, so the fix targets the actual failure point rather than the (already-ruled-out) engine.
FR-001's dual acceptance criterion (price successfully, or explicit "unpriceable" — never a
hard failure) already covers both possible outcomes of that investigation.

**Rationale**: Constitution Principle I forbids fabricating or guessing at a price; since the
duplicate-row anomaly is upstream, read-only vendor data, this codebase's only lever is (a)
confirm no code defect silently swallows this SKU today (confirmed: none in the engine), and
(b) make the non-determinism observable rather than papered over, once the live failure point
is found.

**Alternatives considered**: *Deterministic tie-break (e.g., MIN/MAX price on duplicate rows)*
— rejected for this plan: would change 006's already-established "first row wins" convention
for every SKU with this shape, a wider behavior change than this specific bug report asks for,
and Constitution Principle VI counsels against widening scope ahead of a concrete need. If the
live reproduction in tasks.md finds the duplicate-row non-determinism itself is the user-visible
failure (e.g., the price visibly changes between identical calculations), that becomes a
follow-up decision at implementation time, not a speculative one now.

## §2. Price Change duration-only adjustment (US2, FR-002/003/004)

**Decision**: `frontend/src/lib/priceChange.ts`'s `decideBaselineUpdate()` is the single, already
test-first-covered decision point (007/008 precedent) that needs to change. Today, when content
is unchanged, the function returns `"unchanged"` unconditionally — its own docstring says so
explicitly: *"true whether or not the Duration selection also changed, since Duration alone
never counts as a 'change'"*. That is precisely the bug. The fix: when content is unchanged but
`prior.duration !== newDuration`, return a new outcome (e.g. `"duration_only"`) instead of
`"unchanged"`, so the caller (`WorkspacePage.tsx`) recomputes the comparison total via the
**same `calculate-snapshot` endpoint** the existing `"duration_adjusted"` path already calls
(pricing `prior.selections` at `newDuration`) — never a client-side multiply-by-ratio estimate,
even though the ratio happens to be a simple 12× (12 months) in this app's two-duration world.
The stored baseline's `duration` also advances to the new duration on this path, matching
`"duration_adjusted"`'s existing behavior, so switching back to the original duration
(FR-004) is just another `decideBaselineUpdate` call that finds `prior.duration === newDuration`
again after the user switches back — no separate "remembered original" state needed.

**Rationale**: This keeps the fix inside the one pure, already-unit-tested module built for
exactly this kind of decision (US5/FR-016 in 008), rather than adding duration-branching logic
to `WorkspacePage.tsx` itself. It also automatically satisfies FR-003 (duration-only must use
the real recalculation path) for free, since it's the same code path `"duration_adjusted"`
already uses — no new backend endpoint, no new calculation logic.

**Alternatives considered**: *Special-case duration-only in `WorkspacePage.tsx` directly* —
rejected: duplicates decision logic `priceChange.ts` already owns and tests, splitting the
"what changed" question across two files for no benefit.

## §3. Architecture diagram blank-screen bugs (US3, FR-005/006)

**Decision**: This is a continuation of 008's US1/FR-003, not a new issue — 008's own code
comment (`ArchitectureDiagramPanel.tsx`, the `safely()` wrapper) already documents this
verbatim: *"a defensive mitigation, not a confirmed root-cause fix... the exact trigger...
could not be reproduced live (5 attempts)... flagged for the user to confirm against their own
exact repro, which this tool could not reproduce to verify against directly."* The user has now
supplied exactly that — a specific, scripted repro 008 didn't have:

1. Add an Application Component → add a Service to it → delete the Service → delete the
   Application Component → diagram goes blank (content survives a refresh, so it's a render
   bug, not a data-loss bug).
2. Repeated clicking through diagram elements in some yet-undetermined sequence.

Code review this round surfaced two **new** candidate mechanisms specific to scenario 1, beyond
008's two standing hypotheses (an uncaught event-handler exception — now covered by `safely()`;
unconfirmed viewport/pan-zoom corruption):

- `manualSizeRef` (a plain `useRef<Map>`, not React state) and `ownHeights` (React state) are
  both keyed by Collection id and **never pruned when a Collection is deleted** — harmless in
  isolation (`computeMeasuredHeight`/`childYOffsets` both fall back to
  `estimateComponentHeight(...)` for any id lookup that misses, no `NaN` risk found), but not
  yet ruled out as a contributor in combination with the second mechanism below.
- `useMeasuredHeight`'s `useLayoutEffect` reports a real DOM height after **every** render with
  no dependency array, which (via `reportHeight` → `ownHeights` state → `initialNodes`
  recompute → the `useEffect` that reapplies `initialNodes` to `nodes`) forms a render → effect
  → parent-state-update → render loop that is normally damped by the `prev === next` guards in
  `useMeasuredHeight`/`reportHeight`, but whose timing during a rapid add-then-delete sequence
  (a newly-mounted node's first real measurement landing just as its Collection is deleted)
  has not been traced through to a conclusive verdict either way.

Both are plausible-but-unconfirmed, exactly 008's situation. **Implementation MUST attempt a
live `claude-in-chrome` reproduction of the user's exact scripted sequence (scenario 1) as the
first task for US3**, with browser console instrumentation/breakpoints around
`reportHeight`/`initialNodes`/the `setNodes` effect, before changing any code — repeating 008's
mistake of shipping an unverified guess is explicitly what 008's own research.md warned against.
If reproduced, the fix likely involves pruning `manualSizeRef`/`ownHeights` entries for deleted
Collection ids (cheap, safe regardless) and/or guarding the `initialNodes`-recompute effect
against firing mid-delete. If still not reproducible after a good-faith attempt, document that
explicitly (as 008 did) rather than guessing.

**Rationale**: Constitution Principle VI (no unjustified complexity) argues against a defensive
rewrite of the measurement/layout pipeline speculatively; Principle V's UI carve-out (tests-after
/ live-verified) is exactly the tool for a bug like this — verify the failure live, then fix what
was actually observed.

## §4. Connector/Service data model (US4, FR-007–010)

**Decision**: The Postgres schema **already enforces at most one `SKUSelection` per
`DataConnector`** — `SKUSelection.connector_id` has `unique=True`
(`backend/src/models/orm.py`), so FR-007 needs no schema change. The actual bug is in
`POST /connectors/{connector_id}/sku-selection`
(`backend/src/api/connectors.py::attach_connector_sku`), whose own docstring already says
*"Attach (or replace) the single AWS SKU"* — it explicitly deletes any existing selection and
inserts the new one, which is precisely the "add a second, only one shows up" symptom the user
reported (the second add silently replaces the first, which reads as "only one shows up" from
the user's side). Per the resolved FR-008, this replace-on-conflict behavior changes to
refuse-on-conflict: when `connector.sku_selection is not None`, return `409 Conflict` with a
clear `detail` message instead of deleting and replacing.

No frontend code change is needed to surface that message: `submitNewSku()`
(`WorkspacePage.tsx`) already wraps `api.attachConnectorSku(...)` in try/catch and sets
`skuActionError`, which `ServiceConfigPanel.tsx` already renders via the existing
`ErrorMessage` component (the same inline pattern used everywhere else in the app —
Assumptions). `api/client.ts`'s `request()` already surfaces `HTTPException`'s `detail` string
as `Error.message` verbatim, so the 409's message reaches the user unchanged.

**FR-009/010 (multiple non-overlapping Connectors between the same Collection pair)**: also
needs no backend change — `DataConnector` has no unique constraint on
`(from_collection_id, to_collection_id)`, so the data layer already allows any number of
Connectors between the same pair. The only real work is frontend: `@xyflow/react` renders
multiple edges sharing the same `source`/`target` stacked exactly on top of each other by
default (confirmed against the library's documented behavior), which is what FR-010 forbids.

**Decision (edge routing)**: group `initialEdges` by `(source, target)` pair (order-independent,
so A→B and B→A count as the same pair for offset purposes) and give each edge in a group beyond
the first an increasing perpendicular curve offset (a small, well-established community pattern
for "multiple edges between the same two nodes" — computed in a pure helper function, unit
tested the same way `nodeLayout.ts`'s pure functions are) rather than React Flow's default
straight/bezier path. No new node `Handle`s are needed (nodes keep exactly one source and one
target Handle each) — only the edge path itself is offset.

**Rationale**: Both Postgres constraints already model the corrected rules
(Constitution Principle II — this section's whole fix stays inside "which relationship is
allowed", not new tables); reusing the existing `ErrorMessage`/`skuActionError` plumbing for
FR-008 avoids a new UI surface for what's fundamentally the same "an action was refused, tell
the user why" case every other panel already handles.

**Alternatives considered**: *A new `Handle` per possible duplicate connector, keyed by index*
— rejected: forces every node to pre-declare a speculative number of Handles ahead of knowing
how many parallel Connectors will exist, a real complexity cost FR-010's actual requirement
(visually distinguishable, independently clickable) doesn't need.

## §5. Service search coverage indicator (US5, FR-011–013)

**Decision**: The backend already returns everything needed — `search_catalog()`
(`backend/src/pricing_data/catalog.py`) already computes and returns `total` (008's FR-024), and
`CatalogSearchPanel.tsx` **already reads and displays it** today, just not per FR-011–013's
exact spec: current text is `"({n} of {m} results displayed)"`, positioned *after* (below) the
results list, muted-gray, and hidden entirely once `n === total`. The fix is presentational
only, inside the same component: reword to `"n of m services displayed"`, move it to directly
below the three filter inputs (a fixed element, not inside the scrolling results `<div>`,
matching 008's FR-022 "filter row + status text stay fixed" precedent already established one
`<div>` up), and change its styling to conditionally apply the red/warning class only when
`n < m` (continuing to render, unstyled, when `n === m`, per FR-012) — while continuing to hide
entirely when the search itself returns zero total matches (FR-013, already true today since
`search.data` is only checked when defined and `sortedResults.length < total` is vacuously false
at `total === 0`... explicitly guard this case rather than relying on that being vacuous, so the
"hide at zero" rule survives the reposition intact).

**Rationale**: No backend or data-shape change at all — this is the smallest possible diff that
satisfies FR-011–013, confirmed by reading the actual current implementation rather than
assuming a rewrite was needed.

## §6. Pricing display (US6, FR-014–016)

**Decision**: `PricingPanel.tsx`'s local `formatPrice()` (currently just wraps the numeric
string with fixed decimal formatting, no grouping) gets thousand-separator grouping added —
`Number(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })`
(or equivalent), reused at all three of `formatPrice`'s existing call sites (total, Price
Change, and the per-SKU breakdown loop) — no new formatting function needed, no new call sites.
The `"For {duration}, priced from snapshot {date}"` sentence (FR-015) and the new
`"Data Timestamp: {date}"` line (FR-016) both read from the same existing
`calculation.snapshot_date` field already present on `CalculationResult` — no schema change,
pure JSX edit: delete one `<p>`, add another at the bottom of the column's existing layout.

**Rationale**: `toLocaleString` is a browser-native API already implicitly relied on nowhere
else in this codebase but needs no new dependency, matching Constitution Principle VI (no new
library for a one-call formatting need).

**Alternatives considered**: *A shared `formatCurrency` utility in `lib/`* — worth doing since
`formatPrice` is currently `PricingPanel.tsx`-local and duplicating its logic elsewhere would be
a smell, but there is currently only one component that formats prices, so extracting it now
would be speculative generalization ahead of a second caller (Principle VI). Kept as a
same-file change; revisit if a second price-formatting call site appears.

## §7. Architecture diagram styling, resize, and persistence (US7, FR-017–025)

**Decision, per FR**:
- **FR-017** (hide collection type): `ArchitectureDiagramPanel.tsx` builds each node's `label`
  as `` `${c.name} (${c.type})` `` (two call sites — top-level and nested children) — drop the
  `` (${c.type})` `` suffix, label becomes just `c.name`.
- **FR-018/019** (darker collection border, service border): Tailwind class changes only —
  `VpcNode`'s `border-2 border-primary` and `ApplicationComponentNode`'s conditional
  `border-2 border-primary` (selected) / `border border-border` (unselected) become a visibly
  darker token (verified live against both light/dark theme per artifact-design discipline, not
  assumed from the class name alone); each `ServiceList` `<li>`/`<button>` gains its own
  `border border-border rounded` it doesn't have today.
- **FR-020/021** (resize only from bottom-right, with indicator): `<NodeResizer>` already ships
  a `handleStyle`/`isVisible` API and, per its own docs, a `keepAspectRatio`-independent way to
  restrict which handles render — pass only the bottom-right handle position instead of the
  default all-eight-handles set, so no other edge/corner can be dragged, and no separate
  "remove other handles" logic is needed beyond that one prop change; reuse the diagram's
  existing whole-panel `resize-y` handle's visual treatment (the outer panel `<div>`'s own
  native CSS resize affordance, FR-004 from 008) as the styling reference FR-021 asks for.
- **FR-022** (font-size step-down): follows 008's established convention exactly (research.md
  §10 there) — a further one-step Tailwind utility class reduction (`text-sm`→`text-xs`, etc.)
  across non-diagram components, and a three-step reduction inside
  `ArchitectureDiagramPanel.tsx`'s node/edge label classes specifically — never a global CSS
  `font-size` override (008 explicitly rejected that approach and the reasoning still holds).
- **FR-023** (increased spacing): `VPC_CHILD_SPACING` (`nodeLayout.ts`, currently `10`) and the
  top-level layout's `260`/`220` px grid spacing (`ArchitectureDiagramPanel.tsx`'s
  `initialNodes` positioning) both increase to a visibly larger fixed value — a global constant
  change, not a new per-user setting (see §7a below for why "spacing" isn't independently
  user-adjustable).
- **FR-024** (persistence): see §7a.
- **FR-025** (underline selected name): the selected object's rendered name — Collection label,
  Connector edge label, or Service list item text — gets `underline` conditionally applied based
  on the same `selected`/id-comparison state each already receives as a prop; no new state.

### §7a. What "adjusts diagram spacing... those adjustments MUST persist" (FR-024) actually means

**Important correction to a wrong assumption in spec.md**: the spec's Assumptions section
states FR-024 "reuses the existing per-browser, per-Architecture `localStorage`-based
diagram-layout persistence already established in 005/007/008." **That mechanism does not
exist.** Direct inspection of `frontend/src/lib/` (which holds every other `localStorage`-backed
concern — `columnWidths.ts`, `priorCalculation.ts`) found no diagram-layout file, and
`ArchitectureDiagramPanel.tsx`'s manual-resize state (`manualSizeRef`) is a plain in-memory
`useRef` that is lost on every page reload today — 008 (005-resizable-canvas-boxes/007/008)
only ever made manual resize *work within a session*, never made it survive a reload. This plan
corrects that assumption (spec.md's Assumptions section is updated alongside this research).

Given that, FR-024's actual scope is: **build new `localStorage`-backed persistence** for
per-Collection manual box size (already has in-session state to persist — `manualSizeRef`) and
per-Collection manual position (`ArchitectureDiagramPanel.tsx` currently computes every node's
`position` fresh from its index in the Collections list on every `initialNodes` recompute, which
also means a user's manual node drag is **not preserved even within a session today** — the
`useEffect` that reapplies `initialNodes` to `nodes` only carries over the `selected` flag, not
`position`). "Spacing" (the `VPC_CHILD_SPACING`/grid-gap constants) has no existing
per-Collection or per-user adjustment mechanism anywhere in the codebase and FR-023 already
resolves it as a static, code-level increase (not a runtime user control) — so there is nothing
for FR-024 to persist for "spacing" specifically; the source document's two bullets ("increase
spacing" / "save sizes and spacing") both land on the same static-constant treatment.

**Decision**: a new `frontend/src/lib/diagramLayout.ts`, modeled directly on
`columnWidths.ts`'s existing pattern (a plain object keyed by id, `try/catch`-guarded
`localStorage` read/write under a `cloud-pricing-` prefixed key, silently no-op if unavailable),
keyed **per-browser, per-Architecture** (like `priorCalculation.ts`, not global like
`columnWidths.ts`) since layout is a property of one Architecture's diagram, not the whole app.
Shape: `Record<collectionId, { width: number; height: number; x: number; y: number }>`. Also
fixes the *in-session* position-loss bug identified above as a byproduct, since a persisted
position now needs to survive `initialNodes` recomputes the same way `manualSizeRef`'s size
already does (extending the existing manual-override-preservation pattern to cover `x`/`y`, not
just `width`/`height`).

**Rationale**: Matches the existing `lib/`-module-per-concern convention exactly
(`columnWidths.ts` §7 in 008, `priorCalculation.ts` §6 in 008) rather than inventing a new
persistence pattern; Constitution Principle II (this is `localStorage`-only UI/session state,
not Postgres-worthy user-defined domain data).

**Alternatives considered**: *Persist to Postgres as part of `Collection`* — rejected per
Constitution Principle II and the spec's own Clarifications precedent (008 already decided
column widths/Prior Calculation are `localStorage`-only, not Postgres, for the same reason:
UI/session preference, not domain data); diagram layout is the same category.

## §8. "Add Connector" dialog (US8, FR-026/026a)

**Decision**: `components/ui/select.tsx` (shadcn `Select`) already exists in this codebase and
is the natural fit for the "From Collection"/"To Collection" dropdowns the Clarifications
session specified. `components/ui/dialog.tsx` (shadcn `Dialog`) does **not** exist yet and needs
adding — a standard shadcn primitive, not a new dependency (shadcn/ui components are
copied-in source files per this project's existing convention, not an npm package; `Dialog`
composes on Radix's `@radix-ui/react-dialog`, already an implicit peer of the other Radix-based
shadcn primitives already in this codebase). The dialog's "create" action calls the same
`onCreateConnector(from, to)` prop `ArchitectureDiagramPanel` already exposes and
`WorkspacePage.tsx`'s existing `handleConnect()`/`createConnector` mutation already implements
for the pre-existing select-two-and-connect flow — the new button is a second caller of the same
existing mutation, not new backend interaction. The dropdown options are `collections` (all
Application Components and VPCs in the current Architecture) already available as a prop
one level up; FR-026a's "reject same Collection in both dropdowns" is a pure client-side
disable/validation rule on the dialog's own local state (disable the "confirm" button, or filter
the second dropdown's options to exclude the first's current selection).

**Rationale**: Reuses the existing connector-creation mutation and Collection list verbatim;
the only genuinely new code is the dialog's own presentational state (which two ids are
currently chosen) and the shadcn `Dialog` primitive install.

## §9. AWSDataTransfer region-pair handling (US9, FR-027–030)

**Decision**: `fromRegionCode`/`toRegionCode` are already present, verified directly against the
live Parquet data, inside `product_dim.attributes_json` for every `AWSDataTransfer` row (1021
rows checked) — already surfaced today through `search_catalog()`'s existing `attributes` dict
(`parse_attributes()` already flattens the whole JSON blob into that dict; no new backend field,
no schema change, no new DuckDB column). The label-derivation function
(`` `${fromRegionCode}=>${toRegionCode}` ``) is a small, pure, easily-unit-tested frontend
helper (`frontend/src/lib/awsDataTransfer.ts`, alongside the existing `skuDetail.ts` sibling it
complements), taking a SKU's `service_code` and `attributes` and returning either the derived
label or `null` when `service_code !== "AWSDataTransfer"`.

**Edge case found**: not every `AWSDataTransfer` row has both fields — of 1021 rows, 8 are
missing `fromRegionCode` and 10 are missing `toRegionCode` (internet-bound and CloudFront-edge
transfers, e.g. `toLocation: "External"` / `"Amazon CloudFront"` have no region code on that
side). **Decision**: when either field is absent, fall back to the SKU's existing default
summary (`summaryText()`'s current behavior) rather than rendering a broken `"us-east-1=>"` or
`"=>us-east-1"` label — never fabricate a missing region code (Constitution Principle I applies
to *any* displayed value derived from vendor data, not only prices).

**Decision (integration points)**: the one helper feeds all three FR-028 call sites directly —
`CatalogSearchPanel.tsx`'s `summaryText()` (wrap with a check: use the derived label when
present, else fall through to today's logic), `ArchitectureDiagramPanel.tsx`'s `ServiceList`
item text (same conditional), and `PricingPanel.tsx`'s per-SKU breakdown line (same). FR-029's
dedicated "From region"/"To region" fields are two new `CatalogSearchPanel.tsx` inputs, shown
only when `serviceCode` matches `AWSDataTransfer` (the panel already conditionally renders a
regex error per-field the same way, so conditional-field rendering is an established pattern
here) — each becomes an additional `regexp_matches` filter against `attributes_json`'s
`fromRegionCode`/`toRegionCode`, which requires a **small backend addition**:
`search_catalog()` currently only filters on `service_code`/`product_family`/`text` (top-level
columns), not on individual `attributes_json` keys, so two new optional parameters
(`from_region_code`, `to_region_code`) are needed, each compiling to a
`regexp_matches(json_extract_string(p.attributes_json, '$.fromRegionCode'), ?, 'i')`-style
clause (same case-insensitive-regex convention 008 already established for every other filter),
AND-combined with the existing filters exactly like the others.

**Rationale**: Every other filter already uses the identical regex/AND-combine pattern
(`catalog.py::search_catalog`), so these two new filters are a mechanical extension of existing,
already-tested query-construction logic, not a new querying approach.

## §10. Summary of backend surface changes

Per Constitution Principle IV, every changed API surface needs a matching Pydantic
request/response schema kept in sync with the generated TypeScript types
(`check-api-types` gate):

1. `POST /connectors/{connector_id}/sku-selection` — behavior change only (409 on conflict
   instead of silent replace); response schema (`SKUSelectionOut`) is unchanged. A new error
   response shape is not modeled as a Pydantic schema (FastAPI's `HTTPException` + `detail`
   string is this codebase's existing error-response convention throughout — no precedent for a
   typed error schema to match).
2. `GET /catalog/skus` (`search_catalog`) — two new optional query parameters
   (`from_region_code`, `to_region_code`); request schema/query-param additions only, response
   shape (`CatalogSearchResult`) unchanged (the derived AWSDataTransfer label is a frontend-only
   presentational transform of the existing `attributes` dict already in the response, per §9 —
   no new response field).

No other backend endpoint changes. Every other FR in this feature (US2, US3, US4's frontend
half, US5–US9's frontend halves) is frontend-only, reusing existing backend contracts verbatim.
