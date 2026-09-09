# Quickstart: Five-Column Workspace UI Overhaul

Validates: FR-001–FR-017, SC-001–SC-004. No backend changes — only the frontend dev server
needs to be running.

## Prerequisites

- Frontend dev server running per this repo's existing setup.
- At least one AWS Architecture with a VPC containing a nested Application Component, at
  least one service added to each, and a Data Connector between two Collections — so every
  panel has real content to validate against (reuse an existing test Architecture, or build a
  small one first).

## Scenario 1 — One persistent screen, no page navigation (US1, FR-001/002, SC-001)

1. Load the application. Confirm column 1 shows providers above the Architecture list, with
   the create-new-Architecture control below the list.
2. Select an Architecture from the list.
   - **Expected**: columns 2-5 populate for that Architecture with no page reload or visible
     navigation transition; the URL updates to `/architectures/:id` (bookmarkable), but no
     full-page re-render is visible.

## Scenario 2 — Column 1 collapse/expand (US1, FR-016/017)

1. Click the collapse control at the top of column 1.
   - **Expected**: the panel narrows to icon-only; each provider and Architecture is a
     compact icon; the diagram (column 4) visibly gains width.
2. Hover an icon.
   - **Expected**: the full provider/Architecture name appears (tooltip).
3. Click a provider's or an Architecture's icon while collapsed.
   - **Expected**: it's selected exactly as clicking its label would be expanded.
4. Click the expand control.
   - **Expected**: column 1 returns to its full-width, text-label state.

## Scenario 3 — Collections/search panel, no duplicate service list (US2, FR-003/004/005)

1. Select a Collection. Confirm the Collection-creation controls and Connect/Remove Connector
   actions stay visible at the top of column 2 regardless of how long the search-results list
   below gets.
2. Confirm column 2 shows the selected Collection's name and search controls, but **not** a
   list of its already-added services.

## Scenario 4 — Selecting a service opens column 3 (US3, FR-005/012/014/015)

1. With a Collection selected in the diagram (column 4) that has at least one added service,
   click that specific service where it's listed inside the Collection's box — **not** the
   box itself.
   - **Expected**: column 3 appears, showing that service's attributes and current pricing
     inputs; clicking the box elsewhere still just selects the Collection (column 2 context),
     not this service.
2. From column 2's search results, pick a different service to add.
   - **Expected**: column 3's contents are replaced by the newly picked service's attributes
     and the pricing inputs needed to add it — never showing two services at once.
3. Click empty space (deselect everything).
   - **Expected**: column 3 disappears entirely (collapses) rather than showing an empty
     panel.
4. From column 3, remove the currently-shown already-added service.
   - **Expected**: it's removed from the Collection (same effect as today's list Remove
     control), and column 3 collapses afterward.

## Scenario 5 — A Data Connector's attached service (US3, research.md §8)

1. Select a Data Connector that already has an attached SKU Selection (click its edge on the
   diagram).
   - **Expected**: column 3 automatically shows that attached service's attributes/pricing
     inputs — no separate click needed to reach it, since a Connector has no per-service list
     to click into.

## Scenario 6 — Diagram in its own panel (US4, FR-006)

1. Open an Architecture with nested Collections and Connectors.
   - **Expected**: the diagram renders in a single bounded central panel, distinct from the
     panels beside it.
2. Pan, zoom, select, drag, and resize (both the canvas itself, per `005`, and an individual
   box, per `004`).
   - **Expected**: every interaction works exactly as before this feature.

## Scenario 7 — Duration, Calculate, and results together (US5, FR-007)

1. Set a Calculate duration and click Calculate.
   - **Expected**: the duration selector, Calculate action, total price, any warnings, and any
     unpriceable-item notices all appear together in column 5 — nowhere else on the screen.

## Scenario 8 — Shared visual design system, with the diagram's documented exception (US6, FR-009/010, SC-004)

1. Compare buttons, inputs, and selects across all five panels.
   - **Expected**: consistent shadcn/ui-based styling throughout.
2. Look at common actions (create, delete, connect, edit, search, calculate).
   - **Expected**: each is paired with a Lucide icon.
3. Look at the diagram's own node/edge rendering (column 4's canvas internals).
   - **Expected**: it may reasonably keep its existing (pre-overhaul) styling — this is the
     documented exception, not a bug; the panel chrome around the canvas (border, empty
     state, buttons) still follows the shared design system.

## Scenario 9 — Empty states and deletion resets (Edge Cases, FR-011/012/013)

1. Before selecting any Architecture: confirm columns 2, 4, and 5 show a clear empty/prompt
   state, and column 3 is simply absent (no empty panel shown for it).
2. Delete the currently-selected Collection (or Connector, or Architecture).
   - **Expected**: every panel that depended on it resets to its empty/prompt state (column 3
     collapses instead) rather than showing stale data.

## Notes

- No backend changes — nothing here touches `backend/tests/` or requires re-running the
  backend suite; running the existing suite once at the end is just a regression sanity check
  (unaffected by this feature, per Assumptions).
- Per Constitution Principle V and research.md §10, these scenarios — not new unit tests —
  are the primary verification method for this feature's layout/visual/interaction behavior.
