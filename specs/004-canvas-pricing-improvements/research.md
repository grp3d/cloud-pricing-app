# Phase 0 Research: Canvas & Pricing Improvements

Most technical decisions for this feature reuse `001`-`003`'s established patterns directly.
This document covers the new decisions.

## 1. Duration-scoped calculation: request parameter, not a new endpoint

- **Decision**: `POST /architectures/{id}/calculate` gains one new optional query parameter,
  `duration` (`CalculationDuration` enum: `1_day` | `1_month` | `1_year`, default `1_month`). No
  new endpoint.
- **Rationale**: The calculation is already a single request/response cycle; a duration is just
  another input to the same computation, not a different resource. Matches Constitution
  Principle VI (don't add a service boundary a query parameter already solves). Defaulting to
  `1_month` keeps existing callers (tests, any client that doesn't pass it yet) working with a
  sensible, representative planning horizon rather than requiring a breaking change.
- **Alternatives considered**: A separate `GET /architectures/{id}/calculate/{duration}`
  endpoint — rejected as an unjustified new resource for what's fundamentally one parameter on
  one existing computation.

## 2. Billing-unit classification: pure Python over the `unit` string `003` already resolves

- **Decision**: A new small lookup table (`pricing_data/duration.py`) classifies a billing-unit
  string into `no_period` (Hrs/Minute/Requests-family — treated as a daily rate, spec FR-003),
  `fixed_period` with an explicit `period_days` (Month/GB-Mo-family, `period_days=31` to match
  spec FR-006's month convention — spec FR-004), or `unrecognized` (spec FR-005). Built from the
  actual AWS unit-label variants confirmed present in the real Parquet data during
  clarification (e.g., `Hrs`/`Hours`/`hours`/`hour`/`Hour`/`Hourly`/`Instance-hrs`/`usagehours`/
  `vCPU-Hours`/`seconds` and `Requests`/`Request`/`API Request`/`GB` for `no_period`;
  `Months`/`Month`/`GB-Mo`/`GB-month`/`vCPU-Months`/`IOPS-Mo`/`MBPS-Mo` for `fixed_period`).
  `price_calculation.py` classifies using the same `unit` value `resolve_units` (`003`) already
  resolves for that SKU Selection — no additional DuckDB query needed for classification itself,
  only `resolve_units` now being called from `price_calculation.py` (previously it only called
  `lookup_price`).
- **Rationale**: Reuses data already fetched this request (Constitution Principle VI, "resolve
  once per request" discipline from `001`). A hardcoded lookup table is simple, testable, and
  matches spec's own Assumption that the recognized set is expected to grow incrementally as new
  variants are encountered — no need to parse or infer structure from arbitrary free text.
- **Alternatives considered**: Regex/heuristic parsing of unit strings to infer a period (e.g.,
  detect "Mo" as a substring) — rejected: real data has enough irregular variants (`Instance-hrs`,
  `callme-minutes`) that a substring heuristic would misclassify as often as it helps; an
  explicit table is more auditable and exactly as correct as the entries it contains, with
  incorrect/unrecognized values safely excluded (FR-005) rather than silently mis-guessed.

## 3. Reserved-term proration takes precedence over unit classification

- **Decision**: In `price_calculation.py`, a selection's `pricing_term` is checked first: if
  Reserved (`reserved_1yr`/`reserved_3yr`), its cost is prorated against the commitment's own
  term length (365/1095 days per FR-002) regardless of its billing unit. Only when `pricing_term`
  is `on_demand` does the billing-unit classification (research.md #2) decide between the
  `no_period` (FR-003) and `fixed_period` (FR-004) treatments.
- **Rationale**: Confirmed against the real data that Reserved-term rows are consistently
  `Hrs`-denominated in this dataset, but the *commitment period* — not the hourly rate's own
  granularity — is what the user's clarification established as governing proration for those
  ("prepaid for the year... divided by 365"). Checking `pricing_term` first keeps the two
  proration mechanisms (term-based vs. unit-based) cleanly separated and matches exactly how the
  clarification conversation converged on the final rule.
- **Alternatives considered**: Classifying Reserved-term selections by their unit too (treating
  them as just another `fixed_period` case with `period_days=365`/`1095`) — functionally
  equivalent for the common case, but rejected as a less direct expression of intent: it would
  make `pricing_term` implicitly redundant with a unit-derived period rather than the explicit
  primary signal the clarification established.

## 4. Naming a selection's containing component(s) for warnings (FR-012, FR-013)

- **Decision**: `price_calculation.py` builds an association from each `SKUSelection` to its
  containing Collection name(s) — or, for a Connector-attached selection, a description like
  `"Data Connector between X and Y"` — while it already iterates `architecture.collections` and
  `architecture.connectors` (before flattening into one selections list, as it does today).
  `UnpriceableItem` gains a `components: list[str]` field carrying this, populated for both the
  existing "no price" case and the new FR-005 duration-exclusion case — the same shared list per
  the clarification's "one combined list" decision.
- **Rationale**: The relationship is already fully in scope during the existing iteration —
  no new query, no new join. Reusing `UnpriceableItem` for both exclusion reasons (rather than a
  parallel schema) directly satisfies the clarified requirement that they share one list, and
  avoids Constitution Principle VI complexity (a second, near-identical response shape).
- **Alternatives considered**: A separate `DurationExclusionItem` schema — rejected per the
  clarification's explicit "one combined list" answer; would also duplicate `components`/`reason`
  fields for no real benefit.

## 5. `attributes` on `SKUSelectionOut`: the same batched pattern as `003`'s `unit`

- **Decision**: Add `resolve_attributes(skus)` to `pricing_data/catalog.py` — a batched
  `product_dim.attributes_json` lookup for many `(service_code, sku)` pairs in one DuckDB query,
  mirroring `resolve_units`'s shape exactly (research.md, `003`). `SKUSelectionOut` gains
  `attributes: dict[str, str]` (same shape as `CatalogSKUOut.attributes` from `003`), attached by
  extending the existing `sku_selection_out_with_unit`/`attach_units_to_architecture` helpers in
  `architecture_service.py` to also attach attributes, in the same pass.
- **Rationale**: `003` already solved "resolve read-only catalog data once per request and
  attach it to a response tree" for both `attributes` (search results) and `unit` (any
  SKUSelectionOut) — the only gap is that `attributes` was never attached to an *already-added*
  SKU Selection, only to fresh search results. Extending the existing helpers is a direct,
  minimal-surface-area continuation of that pattern (Constitution Principle VI), needed so the
  canvas diagram (FR-014) can show a service's identifying detail without a second round trip.
- **Alternatives considered**: Having the frontend re-search the catalog for each displayed SKU
  to get its attributes — rejected: N extra network requests for data the backend can attach to
  the response it's already sending, exactly the anti-pattern `003`'s research.md #3 already
  rejected for `unit`.

## 6. Cascading N-level box resize: generalize, don't special-case

- **Decision**: `nodeLayout.ts`'s current one-level-only `estimateVpcHeight` (sums a VPC's direct
  children's heights) is replaced with a single recursive function that computes a height for
  any Collection given its full subtree — a leaf Application Component's height still comes from
  `estimateComponentHeight` (its own SKU Selections, now including any it holds directly),
  and a VPC's (or, if the data model ever allows it, any container's) height is
  `estimateComponentHeight` of its *own* directly-attached services (FR-015) plus the sum of its
  children's *already-computed* heights — however many levels deep that recursion goes. Today's
  data model only ever produces one level of nesting (spec Assumptions), so in practice this
  recurses once, but the function itself makes no assumption about depth.
- **Rationale**: Spec FR-016 explicitly requires cascading through "however many levels deep the
  nesting goes" — writing the function as a genuine recursion (not a two-level special case) is
  the simplest implementation that actually satisfies that requirement today and needs no rework
  if a future feature ever allows deeper nesting (spec Assumptions already flags this feature
  does not itself add that capability).
- **Alternatives considered**: Keep the existing one-level formula and only special-case a second
  level if/when deeper nesting is added later — rejected: `estimateComponentHeight` for a leaf
  and the "sum children" step for a container are already the same recursive shape once a VPC
  also has its own direct services (FR-015) to fold in, so writing it recursively from the start
  is no more complex than the two-level special case would be, and is actually correct per FR-016
  as written.

## 7. Multi-select for connector creation: React Flow's built-in mechanism

- **Decision**: Use `@xyflow/react`'s existing default multi-select interaction (shift/ctrl+click
  adds a node to the selection) together with the `useOnSelectionChange` hook to read the current
  set of selected node ids, driving the enabled/disabled state of the new "Connect" action
  (FR-008, FR-009) — no custom click-tracking or geometry. The existing single-click
  `onNodeClick` handler (which opens the details panel via `selectedCollectionId`) is unaffected
  and continues to fire independently; the two mechanisms coexist since React Flow already
  tracks per-node `selected` state on every click today, just unused until now.
- **Rationale**: The library already does exactly what FR-008/009 need — reusing it is
  Constitution Principle VI directly, and avoids reimplementing selection-count tracking that
  React Flow's own state already provides for free.
- **Alternatives considered**: A custom `Set<string>` of "connector-selected" node ids toggled by
  a dedicated click handler, kept separate from React Flow's own selection state — rejected as
  duplicate state for something the library already tracks natively.

## 8. Restoring drag-to-connect: add the `Handle` elements `003`'s custom node types dropped

- **Decision**: Add explicit `<Handle type="source" ...>` / `<Handle type="target" ...>` elements
  to both `ApplicationComponentNode` and `VpcNode` (`CreateArchitecturePage.tsx`) — the default
  React Flow node type renders these automatically, but a custom node type must render them
  itself, which neither component has done since `003` introduced them.
- **Rationale**: This is the concrete, verified root cause of "it's not possible to draw
  connectors now" (no `.react-flow__handle` elements exist in the DOM for either custom node
  type — confirmed by inspecting the rendered canvas). Restoring them directly fixes FR-011
  without touching anything else about connection handling (`onConnect` was never broken).
- **Alternatives considered**: None — this is a regression fix with one direct cause.

## Outstanding items

None. All Technical Context fields are resolved; no `NEEDS CLARIFICATION` markers remain (all
resolved during `/speckit-clarify`).
