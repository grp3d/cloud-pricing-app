# Research: UI Updates and Corrections

## §1. Diagram bugs (US1, FR-001/002/003) — root-cause findings and recommended approach

Three distinct symptoms, investigated against the current
`frontend/src/components/workspace/ArchitectureDiagramPanel.tsx` (unchanged since 007).

### 1a. Manual box resize doesn't stick (FR-001) — ROOT CAUSE FOUND, targeted patch

**Decision**: Track which nodes the user has manually resized, and skip recomputing
`style.width`/`style.height` for those nodes in the `initialNodes` memo — preserve their
current React Flow node dimensions instead.

**Rationale**: `ArchitectureDiagramPanel.tsx` already renders `<NodeResizer .../>` on every
node and React Flow's own `onNodesChange`/`applyNodeChanges` correctly applies a resize drag
to `nodes` state in the moment. But a `useEffect(() => setNodes(initialNodes), [initialNodes,
setNodes])` unconditionally *resyncs* the entire `nodes` array back to freshly-computed
`initialNodes` every time that memo's dependencies change — and `initialNodes` depends on
`ownHeights`, which changes whenever *any* box's measured content height changes (not just
the one being resized). Each recompute rebuilds every node's `style: { width, height }` from
`computeMeasuredHeight(...)`, discarding whatever the user just dragged. This is a genuine,
reproducible-from-code bug, not a hypothesis: the resize *is* applied, then immediately
overwritten.

**Alternatives considered**:
- *Stop auto-resyncing `nodes` from `initialNodes` at all* — rejected: the resync is what
  makes the *canvas* pick up server-driven changes (a new Collection appearing, a service
  added elsewhere) without a full remount; removing it entirely would break that.
- *Store width/height in the Collection/Connector's own backend record* — rejected per
  Constitution Principle VI: this is view state, not domain data, and 007 already
  established `localStorage`/session-local state as the right home for view-only
  preferences (see §3 below for the same pattern applied to column widths).

### 1b. Boxes don't reliably auto-fit their text (FR-002) — confirmed defect, root cause NOT
fully isolated; needs live diagnosis before a fix is designed

**Decision**: Before writing a fix, add a first implementation task that reproduces this
live in a real, focused browser (not `claude-in-chrome` — see below) with DevTools open, and
records what `ResizeObserver` entries (if any) actually fire. Do not guess at a fix without
that observation.

**Rationale**: This is the same box-sizing system 005 introduced and 007's implementation
pass already investigated in depth (see `005-box-autoresize-not-observed` project memory).
That investigation used temporary `console.log` instrumentation and conclusively found: the
`ResizeObserver` *is* attached correctly (`ref` callback fires with a real element,
`.observe()` is called), but its *callback* never once fired during automated testing,
correlating with `document.hidden === true` / `document.hasFocus() === false` on the
automation tab — a known Chrome behavior (backgrounded tabs get `ResizeObserver`/rAF
throttled). That fully explains why automated testing couldn't observe it working. It does
**not**, on its own, explain the user's confirmation that it *also* doesn't work in their
own, presumably-focused, real browser — so there is a real, unresolved defect here beyond
the tooling limitation already on record. Code review alone already found the wiring
correct once (ref → observe → callback → `setHeight` → `reportHeight` → `ownHeights` →
recompute → `setNodes`); re-reviewing the same code a third time without new information is
unlikely to find what two prior passes didn't. A live console trace is the highest-value
next step.

**Alternatives considered**:
- *Estimate-only fallback (drop the measured-height system, use `estimateComponentHeight`
  unconditionally)* — rejected: this is the pre-005 behavior the whole measured-height
  system exists to fix (research.md/005), and 007's live testing did confirm the *estimate*
  itself under-shoots for 007's now-common two-line box labels (see 007 tasks.md T018's
  note) — reverting to it alone wouldn't satisfy FR-002 even setting the `ResizeObserver`
  question aside.
- *Blind rewrite of the whole measurement system now* — rejected: per Clarifications, a
  rewrite is in scope *if this feature's planning concludes it's needed*, but jumping there
  before a live trace identifies the actual failure would be guessing, not diagnosis-driven
  engineering (Constitution Principle VI: complexity must be justified by a concrete,
  current requirement — "we don't know why the simple version fails yet" doesn't justify a
  rewrite).

### 1c. Clicking empty space inside a VPC makes the whole diagram disappear, needing a
reload (FR-003) — NOT root-caused; needs live diagnosis with DevTools console open

**Decision**: Same as 1b — this is this feature's highest-severity, least-understood bug
and must be the *first* implementation task for User Story 1, reproduced with the browser
console open, before any fix is attempted.

**Rationale**: Static review of every code path a VPC-empty-space click could plausibly
reach (`onNodeClick` → `onSelectCollection`; a zero-distance drag → `onNodeDragStop`, which
already early-returns for any non-`application_component` node, i.e. exactly a VPC; `onPane
Click` → `onDeselectAll`; React Flow's own internal pane/selection handling) found no
obviously-crashing path in the *application* code as written. Two live-diagnosis-only
hypotheses remain open and roughly equally plausible without a real trace: (a) an
uncaught exception thrown inside a React event-handler callback (not the render phase) —
which `frontend/src/components/ErrorBoundary.tsx` cannot catch, since React error boundaries
only catch render/lifecycle errors, not event-handler errors — leaving the app in
whatever partial state the interrupted handler left behind; or (b) the click corrupts React
Flow's own pan/zoom viewport state (rather than removing anything from the DOM), making
every node render far outside the visible canvas — which would *look* like "the diagram
disappeared" and explain why a reload (which re-fits the view) "brings it back", without
any JS error at all. These have different fixes (a needs the specific throw site; b needs
whatever interaction is corrupting viewport state), so guessing between them isn't
productive — the first task must capture which one it actually is.

**Alternatives considered**: *A full diagram-panel rewrite as the first move* — rejected
for the same reason as 1b: per Clarifications, only "if planning concludes it's needed",
and nothing yet establishes that a rewrite (versus a small, once-identified fix) is what
this specific bug needs.

### 1d. Diagram panel height (FR-004)

**Decision**: Increase the resizable canvas wrapper's `min-h-*` ceiling and default height
(currently `min-h-80` / `height: 320` inline, from 005) substantially, and confirm the
existing `resize-y` handle (native CSS `resize`, not a custom drag implementation) isn't
being constrained by a parent flex/height rule elsewhere in `WorkspacePage.tsx`'s layout.

**Rationale**: This is a much narrower, well-understood problem than 1a-1c — the resize
mechanism itself (native CSS `resize: vertical` via Tailwind's `resize-y`) is standard and
not implicated in the other three bugs' failure modes. The reported ceiling ("only 1/3 of
available height") points at either the wrapper's own `min-h-80`/inline `height: 320`
defaults being too conservative, or an ancestor container capping available height before
the resize handle's drag range is reached.

## §2. Regex search matching (US7, FR-020/021) — backend query change

**Decision**: Change `search_catalog()`'s (`backend/src/pricing_data/catalog.py`) three
filter clauses from `p.service_code = ?` / `p.product_family = ?` (exact match) and
`s.service_name ILIKE ? OR p.attributes_json ILIKE ?` (substring) to DuckDB's
`regexp_matches(column, pattern, 'i')` for all three — case-insensitive, RE2-syntax regex
matching, consistent across every field. A malformed pattern raises a DuckDB binder/runtime
exception; catch it at the API layer and return a 400 with a message identifying which
field's pattern is invalid, for the frontend to show inline (FR-021).

**Rationale**: DuckDB (`duckdb>=1.1`, already a dependency) has built-in
`regexp_matches(string, pattern, options)` support using RE2 syntax, so no new dependency is
needed. Making all three fields regex-capable — not just adding a fourth "regex mode"
toggle — directly satisfies "each entry form" from the spec, and is backward-compatible:
ordinary text a user types today (e.g., `AmazonEC2`) is itself a valid, literal regex that
matches the same substring it always did — existing searches keep working unchanged.
Case-insensitive by default matches today's `ILIKE` field's existing behavior (Clarifications
default).

**Alternatives considered**: *Only the free-text field becomes regex-capable, service_code/
product_family keep exact matching* — rejected: the spec (User Story 7, FR-020) explicitly
says "each entry form"; also inconsistent UX (three different matching semantics across
three visually-identical text fields).

## §3. Total match count (US7, FR-024) — new backend query, new response field

**Decision**: Add a `total: int` field to `CatalogSearchResult` (`backend/src/models/
schemas.py`), populated by a second query — `SELECT COUNT(*) FROM ... WHERE {same clause}`
— run alongside the existing paged query in `search_catalog()`. The frontend shows
"(n of m results displayed)" only when `n < total` (`n` = `results.length` actually
returned, capped at 200 per FR-023).

**Rationale**: Today's endpoint only signals "the page was full, so there might be more"
via `next_cursor`, not an exact total — insufficient for FR-024's literal count. A second
`COUNT(*)` query against the same `WHERE` clause and Parquet scan is the direct way to get
an authoritative total (Constitution Principle I: never estimate) without restructuring the
existing query.

**Alternatives considered**: *Derive an approximate total from DuckDB's query planner
statistics* — rejected outright: an estimate is exactly what Principle I forbids for a
number presented to the user as fact.

## §4. Result cap raised to 200 (US7, FR-023)

**Decision**: No backend change. `backend/src/api/catalog.py` already clamps `limit` to
`[1, 200]`; only the frontend's requested/default `limit` parameter changes from 50 to 200.

**Rationale**: Confirmed directly in code (`limit = min(max(limit, 1), 200)`) — 200 is
already the server's ceiling, so this list changed from an original ask of 100 (then 500)
down to exactly matching the existing maximum during clarification — the simplest possible
outcome.

## §5. Duration-adjusted Price Change comparison (US5, FR-015/016/016a) — new
ownership-free "snapshot" calculation endpoint

**Decision**: Add `POST /api/v1/catalog/calculate-snapshot` (naming: under `catalog`, not
`architectures`, since it takes no `architecture_id` and needs no ownership check — it prices
an arbitrary, caller-supplied list of SKU selections, not a persisted Architecture).
Request: `{ duration: CalculationDuration, selections: [{ service_code, sku, pricing_term,
purchase_option, usage_quantity }, ...] }`. Response: the existing `CalculationResult`
schema, unchanged. Implementation: construct a transient (never added to the SQLAlchemy
session, never committed) in-memory `Architecture`/`Collection`/`SKUSelection`-shaped
object graph from the request body and call the existing, untouched
`calculate_architecture_price()` (`backend/src/services/price_calculation.py`) against it —
reusing the exact same pricing-lookup code path every other calculation uses.

**Rationale**: `calculate_architecture_price()` only *reads* scalar attributes off its
`Architecture` argument (`.collections[].sku_selections[].{id,sku,service_code,
pricing_term,purchase_option,usage_quantity}` and `.connectors[].sku_selection`) via plain
Python attribute access — nothing in it requires the object to be a *persisted* row. A
transient SQLAlchemy object (constructed but never `session.add()`-ed) satisfies this
without touching Postgres at all, and — critically for Constitution Principle I — goes
through the *same* authoritative pricing lookups (`lookup_price`, `lookup_reserved_price`,
`resolve_units`) as any other calculation, so the duration-adjusted comparison total is
real, not estimated. The frontend already has everything the request body needs: on every
successful Calculate, it already knows the full set of SKU selections and their pricing
inputs that were just priced (that's what it sent to get the total in the first place) —
this becomes the "Prior Calculation" snapshot persisted per §6 below, submitted to this new
endpoint only when FR-016a's combined architecture-and-duration-change case is detected.

**Alternatives considered**:
- *Snapshot/version the architecture's Collections and SKU Selections in Postgres* —
  rejected: a real schema change and new domain concept for what's fundamentally
  a frontend display feature; violates Principle VI (unjustified complexity) when a stateless
  calculation endpoint fully satisfies the requirement.
- *Approximate the duration adjustment mathematically (scale the old total by a duration
  ratio)* — rejected outright by Constitution Principle I and by 006's own precedent:
  Reserved-term pricing in particular does not scale linearly with duration (a fixed
  upfront fee is prorated differently than a continuous recurring rate), so any such scaling
  would be measurably wrong for a real fraction of architectures.

## §6. Price Change baseline-update decision (US5, FR-015/016/016a) — extractable pure logic

**Decision**: Extract the "did the architecture's own contents change since the last
accepted calculation, independent of Duration" decision into a pure, test-first frontend
module (`frontend/src/lib/priceChange.ts`), mirroring 007's `serviceConfigSelection.ts`
precedent — a `Record`/hash of the current architecture's SKU-selection ids +
pricing-input fields, compared against the same shape stored in the last-accepted Prior
Calculation, is sufficient to answer "changed?" without needing a dedicated
change-tracking event stream.

**Rationale**: Constitution Principle V calls out this exact shape of decision as worth
test-first unit tests (it's genuinely extractable logic, not presentation) — and getting it
wrong in either direction (baseline resets on a harmless re-Calculate, or a real edit gets
silently ignored) is the one part of this feature's pricing display users would notice as
outright incorrect, not just unpolished.

**Alternatives considered**: *Track "changed" via an explicit dirty-flag set on every
mutation call-site (add SKU, remove SKU, etc.)* — rejected: more call sites to keep in sync
by hand, more places to forget the flag, versus a single comparison function that only needs
"the current set of selections" and "the last-priced set of selections" as input.

## §7. Column width / Prior Calculation persistence (US4/US5, FR-013/016b) —
`localStorage` schema

**Decision**: One `localStorage` key per concern, namespaced under the existing
`cloud-pricing-` prefix already used for the anonymous per-browser user id
(`frontend/src/api/client.ts`): `cloud-pricing-column-widths` (a plain `{ [columnId]:
number }` map) and `cloud-pricing-prior-calculation-{architectureId}` (one entry per
Architecture, so switching Architectures never cross-contaminates baselines — Edge Cases).

**Rationale**: Matches the existing, already-established pattern for lightweight,
backend-free, per-browser state in this codebase exactly — no new persistence mechanism,
no new dependency. Keying Prior Calculation by Architecture id directly satisfies the edge
case "switching Architectures doesn't fabricate or carry over a change."

**Alternatives considered**: *A single JSON blob under one key for all UI preferences* —
rejected: no benefit over one-key-per-concern here, and a corrupted/oversized blob would
risk losing unrelated preferences together; per-key storage degrades independently.

## §8. Column 1-3 collapsibility (US2, FR-006) and column 3 always-present (US2, FR-005)

**Decision**: Extend `ProviderArchitecturePanel.tsx`'s existing `expanded` boolean +
collapse/expand icon pattern (007) to `CollectionsPanel.tsx` and `ServiceConfigPanel.tsx`
verbatim — same local `useState`, same two-icon top-right control, same shadcn `Tooltip`
hover-reveal. `ServiceConfigPanel.tsx`'s current `if (!selection) return null;` (007,
FR-012) is replaced with rendering the panel's chrome (header, border) unconditionally and
only conditionally rendering its *content* (`SkuDetail`/`PricingInputsForm` vs. nothing).

**Rationale**: Directly reuses a proven, already-shipped pattern — no new interaction
design needed, just wider application of one that already works (007 tasks.md T012 already
confirmed the tooltip mechanism works after the `Button` ref-forwarding fix).

**Alternatives considered**: *A single shared `CollapsiblePanel` wrapper component* —
worth considering during implementation for the three now-duplicated collapse/expand
blocks, but not required by any FR; left as an implementation-time judgment call, not a
planning decision, per Constitution Principle VI (don't build the abstraction until three
near-identical copies make the duplication itself the concrete problem).

## §9. Column width dragging (US4, FR-012)

**Decision**: A thin draggable divider between each pair of adjacent columns, implemented
with plain pointer-event handlers (`pointerdown`/`pointermove`/`pointerup`) updating each
column's width in `WorkspacePage.tsx` state (persisted per §7), with `min-width` clamps
per column matching each panel's own minimum usable width (its collapsed-rail width, since
that's already a known lower bound every column must fit).

**Rationale**: A native, dependency-free drag-to-resize interaction; the existing codebase
has no drag-resize library, and this is a well-understood ~30-line interaction that doesn't
justify adding one (Constitution Principle VI). Using each column's already-defined
collapsed-rail width as its minimum is the natural floor and needs no new design decision.

**Alternatives considered**: *A CSS Grid with `resize` on grid tracks* — no direct browser
support for resizing individual grid tracks via native `resize`; would still need JS pointer
handling, so this doesn't actually save the implementation the Decision already assumes.

## §10. Sky color scheme (US6, FR-019) and font-size step-down (US6, FR-018)

**Decision**: Regenerate the shadcn/ui theme tokens in `frontend/src/index.css` (the
`:root`/`.dark` OKLCH custom-property blocks 007 generated) using Radix's "sky" scale in
place of the current neutral scale, keeping the same token *names* (`--primary`,
`--background`, etc.) so no component code changes — only the CSS custom-property values
change. Font-size step-down (FR-018) is a search-and-replace of each Tailwind text-size
utility class one step down (`text-base`→`text-sm`, `text-sm`→`text-xs`, etc.) across the
touched components — not a global CSS override of `font-size`, since shadcn/Tailwind
components rely on the *utility classes* actually present, not an inherited base size, for
most of their sizing.

**Rationale**: This is exactly how 007 already generated the current (neutral) theme via
the shadcn CLI's own token-based approach — swapping the palette is a data change to that
same token system, not a new mechanism. Per-class step-down (rather than a root
`font-size` override) avoids fighting Tailwind's `rem`-relative utility scale and keeps
every component's own explicit sizing intent legible in its source, matching how 007's
components were already written.

**Alternatives considered**: *A CSS `zoom`/root `font-size` scale-down* — rejected: would
scale non-text sizing (padding, icons, borders defined in `rem`) along with text, which is
a much bigger, less-controlled visual change than "reduce font sizes" asked for.

## §11. Provider icons (US3, FR-008)

**Decision**: Import the two existing PNGs (`screenshot-samples/gcp_icon.png`,
`screenshot-samples/azure_icon.png`) as static Vite assets into
`frontend/src/assets/providers/` (copied into the repo, not referenced from outside
`frontend/`, since `screenshot-samples/` lives outside `frontend/`'s Vite root and isn't
served) and render them via `<img>` in `ProviderArchitecturePanel.tsx`'s collapsed state,
replacing the current generic Lucide `Cloud` icon. AWS has no equivalent asset yet
(Assumptions) — implementation blocks on that specific icon being supplied; the AWS
collapsed-icon change is the one part of FR-008 not implementable until then.

**Rationale**: Vite's standard static-asset import (`import gcpIcon from
"../../assets/providers/gcp_icon.png"`) is the existing project's normal way to bundle an
image (no new tooling); copying into `frontend/src/assets/` (rather than referencing the
sibling `screenshot-samples/` directory directly) keeps the frontend's build self-contained
and matches Vite's expectation that importable assets live inside its project root.
