# Phase 0 Research: Service Selection Improvements

Most technical decisions for this feature reuse `001`/`002`'s established patterns directly.
This document covers the new decisions.

## 1. Exposing richer SKU detail generically

- **Decision**: Add `attributes: dict[str, str]` to `CatalogSKUOut` — the SKU's full
  `product_dim.attributes_json`, parsed server-side into a plain key/value map. No per-service
  special-casing (e.g., no hardcoded "if EC2 then show vcpu/memory" logic).
- **Rationale**: `attributes_json`'s shape varies per AWS service (confirmed during `001`'s
  research — EC2 has `vcpu`/`memory`/`networkPerformance`/etc., other services have entirely
  different keys), and per Constitution Principle III a future non-AWS provider's catalog would
  have its own shape again. A generic map is the only representation that doesn't need updating
  every time a new service or provider is added.
- **Alternatives considered**: A curated, per-service-type set of "important" fields chosen
  server-side — rejected: brittle (breaks for services not anticipated), and violates
  Principle III by baking AWS-specific field names into the backend.

## 2. Where richer detail is shown vs. how much

- **Decision**: Search result rows show a short, generic detail line built client-side from
  whichever of a small set of common candidate keys (`instanceType`, `memory`, `vcpu`,
  `operatingSystem`, `storage`, `group`, `groupDescription`) are present in that SKU's
  `attributes` map — a handful of values, not a dump. The full `attributes` map is shown as a
  labeled key/value list at the "Selected: ..." confirmation step (`SkuDetail.tsx`), where
  there's room and it's the actual decision point before entering pricing inputs.
- **Rationale**: Directly satisfies spec FR-001 (distinguish list results) and FR-002 (full
  detail at confirmation) without overwhelming the compact list view. The candidate-key list is
  a frontend display choice, not a backend contract — adding a new common key later is a
  frontend-only change.
- **Alternatives considered**: Showing the full attributes map inline in every list row —
  rejected, would make the list unreadable for SKUs with 20+ attributes (observed in `001`'s
  data exploration).

## 3. Resolving billing units without a new endpoint

- **Decision**: Add `unit: str | None` to both `CatalogSKUOut` (search results — resolved via
  `product_dim` regardless of term/purchase_option, since a SKU's metering unit doesn't vary by
  commitment term) and `SKUSelectionOut` (resolved from the SKU it references). No new endpoint.
  For the single-object endpoints (`POST`/`PATCH .../sku-selections`, `POST
  .../connectors/{id}/sku-selection`) the unit is resolved with one DuckDB lookup for that one
  SKU. For `GET /architectures/{id}` (which returns a whole nested tree of SKU Selections), units
  for every distinct SKU referenced are resolved in a single batched DuckDB query, then attached
  to each nested `SKUSelectionOut` in the response tree before it's returned — the same
  "resolve once per request, not once per row" discipline `001` already used for snapshot-date
  resolution.
- **Rationale**: `unit` is not a stored fact (it lives only in the read-only Parquet data,
  Constitution Principle II), so it can't be served by Pydantic's automatic ORM-attribute
  serialization the way stored columns are — every endpoint returning a `SKUSelectionOut` must
  explicitly attach it. Batching the tree-endpoint's lookups avoids N+1 DuckDB queries for an
  Architecture with many SKU Selections.
- **Alternatives considered**: A separate `GET /sku-selections/{id}/unit` endpoint the frontend
  calls per selection — rejected: N frontend requests instead of one attached field, more
  network overhead, more frontend state to manage, no benefit over attaching it to the existing
  response.

## 4. Application Component nodes: custom rendering + estimated sizing

- **Decision**: A custom React Flow node type renders an Application Component's name plus a
  list of its SKU Selections. Height is a computed *estimate* — `baseHeight +
  max(1, skuCount) * rowHeight` — set explicitly as the node's `style.height`, not left to
  organic CSS auto-sizing. VPC nodes' height is now the sum of their children's estimated
  heights (plus the VPC's own header/spacing) instead of `002`'s original fixed
  50px-per-child assumption. Both computations live in a new pure module (`nodeLayout.ts`) with
  no DOM/React Flow dependency, so they're directly unit-testable.
- **Rationale**: React Flow's parent/child nodes are independently positioned graph nodes, not
  DOM children of their parent's own render — the library does not auto-flow child node layout
  for you, so a parent's size and its children's positions must still be computed ahead of
  render. An *estimate* (rather than measuring actual rendered pixel height via
  `useNodesInitialized`/a post-render measurement pass) is deliberately simpler and sufficient:
  the spec asks for the box to "grow or shrink automatically" to roughly fit its contents
  (FR-007), not for pixel-perfect measurement.
- **Alternatives considered**: Measuring actual rendered DOM height after paint and re-laying
  out — rejected as unjustified complexity (Principle VI) for a requirement that only asks for
  reasonable auto-fit, not exact measurement; would also add a render-then-relayout flicker.

## 5. Manual resize: `NodeResizer`, and how it coexists with auto-fit

- **Decision**: Attach `@xyflow/react`'s `NodeResizer` to both the VPC node type and the
  Application Component node type. Its `minWidth`/`minHeight` props are set to that node's
  current *content-required* size from `nodeLayout.ts` (satisfying FR-011's VPC minimum-size
  guard directly through the library's own constraint, no custom validation code). A manual
  resize changes that node's size in local React Flow state immediately; it is superseded the
  next time `initialNodes` is recomputed from fresh Collection data (already happens on every
  `invalidate()` after any mutation, per `001`/`002`'s established pattern) — matching the
  spec's Assumption that manual sizing is a per-session convenience, not a persisted override.
- **Rationale**: Reuses the library's own resize mechanism (Principle VI) instead of building
  custom drag-to-resize handles and math. The "reset on next data change" behavior needs no new
  bookkeeping — it falls out for free from the `initialNodes`-recompute pattern both prior
  features already rely on.
- **Alternatives considered**: Tracking a per-node "was this manually resized, and at what
  content-count" map so a manual resize could survive until content actually changes (rather
  than any data refresh) — rejected as more state to maintain for a difference the spec doesn't
  actually require; the simpler "resets on any data refresh" behavior already satisfies every
  stated acceptance scenario and edge case.

## Outstanding items

None. All Technical Context fields are resolved; no `NEEDS CLARIFICATION` markers remain.
