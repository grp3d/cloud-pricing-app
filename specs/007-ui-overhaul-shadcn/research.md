# Research: Five-Column Workspace UI Overhaul

## 1. Tailwind CSS setup

**Decision**: Tailwind CSS v4 via the `@tailwindcss/vite` plugin — a single Vite plugin line
plus one CSS entry file (`@import "tailwindcss";`), no `tailwind.config.js` or PostCSS config
needed for the baseline setup (v4's CSS-native `@theme` directive covers the small amount of
customization this app needs, e.g. mapping the five panels' spacing scale).

**Rationale**: Directly serves the explicit "code simplicity... priority over forced package
usage" instruction (spec Clarifications) — v4's setup has fewer moving parts (one plugin, one
CSS file) than v3's PostCSS pipeline, and it's what a fresh Tailwind install produces today.

**Alternatives considered**: Tailwind v3 + PostCSS + `tailwind.config.js` — rejected as more
config surface for no benefit on a fresh install with no legacy v3-only plugin dependency.

## 2. shadcn/ui setup

**Decision**: shadcn/ui's CLI (`npx shadcn@latest init`, then `add` per component) scaffolds
plain, committed component source files into `frontend/src/components/ui/` — it is not an npm
runtime dependency, just a code generator over Radix UI primitives + Tailwind. Requires a
`@/*` → `frontend/src/*` path alias (added to `tsconfig.json` and `vite.config.ts`) and a
`components.json` config, both shadcn/ui conventions. Only the specific primitives this
feature actually needs are added (e.g. `button`, `input`, `select`, `card`, `tooltip`,
`scroll-area`, `separator`) — not the full component catalog.

**Rationale**: This is shadcn/ui's own documented model (source-in-your-repo, not a
black-box package), which is itself aligned with "code simplicity and maintainability" — the
generated components are plain, readable TSX this codebase owns and can trim or modify
directly, not an opaque dependency to work around.

## 3. Icons

**Decision**: `lucide-react` (the React bindings for Lucide, the icon set explicitly
requested) as a normal npm dependency; individual icons imported per use
(`import { Plus, Trash2 } from "lucide-react"`), which tree-shakes cleanly.

**Rationale**: Directly serves FR-010; no alternative considered since the icon set was
explicitly named.

## 4. One persistent workspace shell, still URL-addressable

**Decision**: Both existing routes (`/` and `/architectures/:architectureId`) render the same
top-level `WorkspacePage` component (replacing today's separate `LandingPage` and
`CreateArchitecturePage` route elements). `WorkspacePage` reads `architectureId` from the URL
when present; selecting a different Architecture in column 1 calls React Router's `navigate()`
to update the URL to `/architectures/:id`, which — because both routes resolve to the same
component — does not unmount/remount the shell or reload the page, only re-renders with the
new `architectureId`.

**Rationale**: Satisfies User Story 1's "no page reload or URL-driven navigation required to
see it" (the visual update is instant, no transition) while still keeping Architectures
individually bookmarkable/shareable via URL and preserving browser back/forward — dropping
routing entirely would lose that for no requirement that asked for it.

**Alternatives considered**: A single route with `selectedArchitectureId` as pure client
state, no URL reflection at all — rejected as an unforced regression (today's
`/architectures/:id` links are shareable; nothing in the spec asks to give that up).

## 5. State ownership: one owning page, five presentational panels

**Decision**: `WorkspacePage` owns all cross-panel state and mutations — mostly relocated
verbatim from today's `CreateArchitecturePage`'s internal state/mutations plus `LandingPage`'s
provider/Architecture-list state — and passes the relevant slice plus callbacks down as props
to five focused panel components (`ProviderArchitecturePanel`, `CollectionsPanel`,
`ServiceConfigPanel`, `ArchitectureDiagramPanel`, `PricingPanel`). No new state-management
library or React Context is introduced.

**Rationale**: Five sibling panels one level below a single owning page is a shallow, easily
readable prop-passing shape — introducing Context or a state library here would be exactly
the kind of unjustified complexity Constitution Principle VI (Simplicity & YAGNI) rules out.
This also lets almost all of the existing, already-hardened (002-006) query/mutation logic
move with minimal change, rather than being rewritten.

## 6. Unifying "what column 3 shows" into one selection type

**Decision**: Replace today's two separate pieces of state — `pickedSku` (a catalog result
chosen to add) and `editingSkuSelectionId` (an existing SKU Selection being edited) — with one
union type owned by `WorkspacePage`:

```ts
type ServiceConfigSelection =
  | { kind: "existing"; skuSelectionId: string }
  | { kind: "new"; catalogSku: CatalogSKU }
  | null;
```

**Rationale**: FR-015 ("at most one service's configuration at a time... replaces rather than
stacks") is a structural guarantee with one selection slot, not a convention two separate
pieces of state have to be manually kept in sync to honor. `ServiceConfigPanel` renders
nothing when this is `null` (FR-012's collapse behavior) and one of two views otherwise.

## 7. Individual per-service click targets on the diagram (FR-014)

**Decision**: Each service listed inside `ServiceList` (used by both `ApplicationComponentNode`
and `VpcNode`) becomes its own clickable element, calling a new `onSelectService(skuSelectionId)`
callback threaded through the node's `data` (the same pattern 005 already established for
`onMeasuredHeight`). Its click handler calls `event.stopPropagation()` so the click is not also
interpreted as a click on the containing box (which selects the Collection as a whole, existing
002-006 behavior) — clicking a listed service sets both the `ServiceConfigSelection` (column 3)
and, as a convenience default, that service's containing Collection as the current column-2
selection, so column 2 shows matching context.

**Rationale**: This is the one place (per spec Assumptions) this feature adds genuinely new
interactive behavior rather than relocating existing behavior — `stopPropagation` is the
standard, minimal way to let a child element capture a click a parent element also listens for,
without touching the parent's own existing `onNodeClick` handling.

## 8. A Data Connector's attached service has no "box" to click inside

**Decision**: Selecting a Data Connector (clicking its edge — existing behavior) sets
`selectedConnectorId` as today; if that Connector already has an attached SKU Selection, the
same click also sets `ServiceConfigSelection` to `{ kind: "existing", skuSelectionId: ... }`
for it, automatically.

**Rationale**: A Connector holds at most one attached service and isn't a "box" with a list
inside it (spec FR-005/Assumptions) — there's no separate per-service target to add the way
FR-014 adds one for a Collection's box, so the Connector's own existing click target has to
double as that entry point.

## 9. Panel-1 collapse/expand state

**Decision**: `expanded: boolean` local state inside `ProviderArchitecturePanel` (or lifted to
`WorkspacePage` if column 4's diagram ever needs to react to the width change, e.g. to refit
the view — a small, cheap decision left to implementation). Not persisted across reloads.

**Rationale**: Matches this app's existing precedent (canvas resize, manual box resize — 005)
of per-session, non-persisted UI convenience state; spec Assumptions don't ask for
persistence, and adding it would be unrequested scope.

## 10. Testing approach

**Decision**: Per Constitution Principle V's explicit carve-out ("UI-only presentational code
MAY follow tests-after where a test-first cycle adds no verification value"), this feature —
a layout and visual-design-system change with no pricing computation or data-relationship
logic — is validated primarily through live browser verification (`claude-in-chrome`) against
`quickstart.md`'s scenarios, matching `005`'s established precedent. Existing unit-tested
domain components (`CatalogSearchPanel`, `PricingInputsForm`, `SkuDetail`, `usageQuantityHint`,
`connectorSelection`, `nodeLayout`, `dropTargetDetection`) keep their existing tests passing
unchanged, since their props/behavior contracts don't change — only their internal
markup/styling and which parent renders them. Any newly-extracted pure logic (e.g., if the
Collection-vs-Connector-vs-nothing decision for column 2's header, or the
`ServiceConfigSelection` transitions, are pulled into standalone functions) gets test-first
unit tests, following the `nodeLayout.ts`/`connectorSelection.ts` precedent — the same
test-first-for-logic, live-verify-for-presentation split this codebase already uses.

## 11. No data-model, contracts, or backend changes

**Decision**: Confirmed against spec Assumptions — this feature touches `frontend/` only. No
`data-model.md` or `contracts/` are produced (nothing to document); `backend/` is untouched.
