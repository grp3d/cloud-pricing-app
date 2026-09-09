---

description: "Task list for Five-Column Workspace UI Overhaul"
---

# Tasks: Five-Column Workspace UI Overhaul

**Input**: Design documents from `/specs/007-ui-overhaul-shadcn/`

**Prerequisites**: plan.md, spec.md, research.md, quickstart.md (all present). No
`data-model.md`/`contracts/` — no data-model or API-contract changes. `backend/` is
untouched throughout.

**Tests**: Minimal, by design (Constitution Principle V's presentational-code carve-out,
research.md §10) — this is layout/visual-system work, not pricing or data-relationship
logic. The one genuinely new piece of pure logic (`ServiceConfigSelection`) gets test-first
unit tests; every other user story is validated live against `quickstart.md`
(`claude-in-chrome`), matching `005`'s precedent.

**Organization**: Setup (tooling) and Foundational (the shell + state relocation) come
first, since every panel is rendered from `WorkspacePage` and needs its state already
present. The five P1 user stories are then sequenced US1 → US4 → US2 → US3 → US5 — not
spec.md's story-number order — because User Story 3 (service configuration) can't be
meaningfully validated until User Story 4 (the diagram's new per-service click target)
exists; every other P1 ordering choice among themselves doesn't matter. User Story 6 (P2,
the cross-cutting visual-consistency pass) comes last since it touches every other panel's
finished markup.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: `US1`-`US6`, matching `spec.md`
- File paths are relative to the repository root and follow `plan.md`'s Project Structure

## Phase 1: Setup (Tooling)

**Purpose**: Get Tailwind CSS, shadcn/ui, and Lucide into the project before anything is
built with them.

- [ ] T001 Install and configure Tailwind CSS v4 (`@tailwindcss/vite` plugin) in
      `frontend/vite.config.ts`; add the Tailwind entry (`@import "tailwindcss";`) to
      `frontend/src/index.css` (or equivalent); verify a utility class renders in the app
      (research.md §1)
- [ ] T002 Install and initialize shadcn/ui in `frontend/` (`npx shadcn@latest init`),
      adding the `@/*` → `src/*` path alias to `frontend/tsconfig.json` and
      `frontend/vite.config.ts`, producing `frontend/components.json` (research.md §2;
      depends on T001)
- [ ] T003 [P] Add the shadcn/ui primitives this feature needs into
      `frontend/src/components/ui/` via the shadcn CLI: `button`, `input`, `select`, `card`,
      `tooltip`, `scroll-area`, `separator` (depends on T002)
- [ ] T004 [P] Install `lucide-react` in `frontend/package.json` (research.md §3)

## Phase 2: Foundational (Shell + State Relocation)

**Purpose**: Build the empty five-column shell and move all existing state/queries/
mutations into it, so every user story phase below only has to fill in one panel's content.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T005 [P] Write tests-first for `ServiceConfigSelection` (the union type replacing
      today's separate `pickedSku`/`editingSkuSelectionId`, research.md §6) in
      `frontend/tests/unit/serviceConfigSelection.test.ts` (new): construction of both the
      `"existing"` and `"new"` variants, and that a fresh selection always fully replaces
      any prior one (no merging) — whatever shape the module takes beyond the bare type
- [ ] T006 Implement `ServiceConfigSelection` in `frontend/src/lib/serviceConfigSelection.ts`
      (new; depends on T005 — makes it pass)
- [ ] T007 Create the five-column shell in `frontend/src/pages/WorkspacePage.tsx` (new): a
      CSS grid/flex layout (Tailwind utility classes) with five placeholder panel slots,
      wrapped in `ReactFlowProvider` (depends on T001)
- [ ] T008 Point both routes in `frontend/src/App.tsx` (`/` and
      `/architectures/:architectureId`) at `WorkspacePage` (research.md §4; depends on T007)
- [ ] T009 Relocate all state, queries, and mutations from `frontend/src/pages/LandingPage.tsx`
      and `CreateArchitecturePageInner` (in `frontend/src/pages/CreateArchitecturePage.tsx`)
      into `WorkspacePage.tsx`: providers/Architectures query + create + delete;
      Collections/Connectors/calculation queries + mutations;
      `selectedCollectionId`/`selectedConnectorId`/`selectedNodeIds`/`pendingDeleteCollectionId`/
      `pendingDeleteConnectorId`/`newCollectionType`/`newCollectionName`/`calculationDuration`/
      `calculation`/`calculationError`/`actionError`/`skuActionError`/`ownHeights`; replace
      `pickedSku`/`editingSkuSelectionId` with `ServiceConfigSelection` (T006). Pass
      placeholder/unused props to the five empty slots from T007 for now (research.md §5;
      depends on T006, T008)
- [ ] T010 Delete `frontend/src/pages/LandingPage.tsx` and
      `frontend/src/pages/CreateArchitecturePage.tsx` — fully superseded (depends on T009)

**Checkpoint**: the app builds and runs on the new shell with five empty placeholder panels
— no user-visible functionality yet; that's what the phases below add.

---

## Phase 3: User Story 1 - Choose a provider and Architecture from one persistent panel (Priority: P1) 🎯

**Goal**: Column 1 replaces the landing page, and is collapsible to an icon rail.

**Independent Test**: `quickstart.md` Scenarios 1-2.

- [ ] T011 [US1] Build `frontend/src/components/workspace/ProviderArchitecturePanel.tsx`:
      provider tabs, the Architecture list, and the create-Architecture control below the
      list (not above it, FR-002) — using shadcn `button`/`card`/`scroll-area`, consuming
      the state/callbacks `WorkspacePage` already owns (T009)
- [ ] T012 [US1] Add collapse/expand to `ProviderArchitecturePanel.tsx`: local `expanded`
      boolean state; two Lucide icon toggle controls at the top of the panel; while
      collapsed, providers and Architectures render as compact icons with a shadcn
      `tooltip` revealing the full name on hover, and remain individually clickable
      (FR-016/017)
- [ ] T013 [US1] Mount `ProviderArchitecturePanel` as column 1 in `WorkspacePage.tsx`
      (depends on T011, T012)
- [ ] T014 [US1] Live-verify `quickstart.md` Scenarios 1-2 via `claude-in-chrome` (depends
      on T013)

**Checkpoint**: Column 1 is fully functional and independently testable.

---

## Phase 4: User Story 4 - View the assembled architecture in its own panel (Priority: P1) 🎯

**Goal**: The existing React Flow canvas relocates into its own panel and gains
individually-clickable per-service targets.

**Independent Test**: `quickstart.md` Scenario 6.

**Note**: Built before User Story 2/3 below despite matching spec.md's later numbering —
User Story 3 (service configuration) can't be meaningfully validated without the
per-service click target this phase adds.

- [ ] T015 [US4] Relocate the React Flow canvas — `nodeTypes`, `ApplicationComponentNode`,
      `VpcNode`, `ServiceList`, the `initialNodes`/`initialEdges` construction,
      `onConnect`/`onNodeDragStop`/`onEdgeClick`, and the resizable canvas wrapper `<div>`
      (005) — from the deleted `CreateArchitecturePage.tsx` (recovered from git history if
      needed) into `frontend/src/components/workspace/ArchitectureDiagramPanel.tsx` (new),
      consuming state/callbacks from `WorkspacePage`
- [ ] T016 [US4] Add per-service click targets in `ServiceList` (in
      `ArchitectureDiagramPanel.tsx`): each listed service becomes its own clickable
      element, calling a new `onSelectService(skuSelectionId)` threaded through the node's
      `data` (mirroring `onMeasuredHeight` from `005`) with `event.stopPropagation()` so the
      click isn't also interpreted as a click on the containing box; selecting a service
      also sets its containing Collection as the current column-2 selection (research.md
      §7; depends on T015)
- [ ] T017 [US4] Mount `ArchitectureDiagramPanel` as column 4 in `WorkspacePage.tsx`, wiring
      `onSelectService` to set `ServiceConfigSelection` (T006) to
      `{ kind: "existing", skuSelectionId }` (depends on T016)
- [ ] T018 [US4] Live-verify `quickstart.md` Scenario 6 — including every existing canvas
      interaction from `002`-`005` (pan, zoom, select, drag, individual-box resize, canvas
      resize) — via `claude-in-chrome` (depends on T017)

**Checkpoint**: Column 4 is fully functional; the new per-service click target exists and
is ready for User Story 3 to consume.

---

## Phase 5: User Story 2 - Manage Collections, Connectors, and service search in one panel (Priority: P1) 🎯

**Goal**: Column 2 shows the fixed Collection/Connector controls and search, with no
duplicate list of already-added services.

**Independent Test**: `quickstart.md` Scenario 3, plus Scenario 5's Connector half.

- [ ] T019 [US2] Build `frontend/src/components/workspace/CollectionsPanel.tsx`: a fixed-top
      section with Collection-creation controls and Connect/Remove Connector actions
      (shadcn `button`/`input`/`select`), and below it, the selected Collection's/
      Connector's name plus the reused, unchanged `CatalogSearchPanel` — deliberately no
      list of already-added services (FR-003/004/005)
- [ ] T020 [US2] Wire Connector selection in `WorkspacePage.tsx`: clicking a Connector edge
      (now in `ArchitectureDiagramPanel`, T015's relocated `onEdgeClick`) sets
      `selectedConnectorId`, and — if that Connector already has an attached SKU
      Selection — also sets `ServiceConfigSelection` (T006) to
      `{ kind: "existing", skuSelectionId }` for it (research.md §8; depends on T015)
- [ ] T021 [US2] Mount `CollectionsPanel` as column 2 in `WorkspacePage.tsx` (depends on
      T019)
- [ ] T022 [US2] Live-verify `quickstart.md` Scenario 3 and the Connector half of Scenario 5
      via `claude-in-chrome` (depends on T020, T021)

**Checkpoint**: Column 2 is fully functional and independently testable.

---

## Phase 6: User Story 3 - Configure a selected service in its own panel (Priority: P1) 🎯

**Goal**: Column 3 shows exactly one selected service's attributes/pricing inputs, or
collapses entirely.

**Independent Test**: `quickstart.md` Scenario 4, plus Scenario 5's remaining half.

- [ ] T023 [US3] Build `frontend/src/components/workspace/ServiceConfigPanel.tsx`: renders
      nothing (collapsed) when `ServiceConfigSelection` (T006) is `null` (FR-012); otherwise
      renders the reused, unchanged `SkuDetail` + `PricingInputsForm` for either the
      `"existing"` or `"new"` case, plus — for `"existing"` — a Remove control invoking the
      existing delete-SKU-Selection mutation (FR-005's remove-capability addendum)
- [ ] T024 [US3] Wire `CatalogSearchPanel`'s "Add" pick (rendered inside `CollectionsPanel`,
      T019) to set `ServiceConfigSelection` to `{ kind: "new", catalogSku }` in
      `WorkspacePage.tsx`, replacing the old `pickedSku` wiring (depends on T019)
- [ ] T025 [US3] Mount `ServiceConfigPanel` as column 3 in `WorkspacePage.tsx`, positioned
      between `CollectionsPanel` and `ArchitectureDiagramPanel` (depends on T017, T023,
      T024)
- [ ] T026 [US3] Live-verify `quickstart.md` Scenario 4 (including the collapse behavior and
      the Remove control) and the remaining half of Scenario 5 via `claude-in-chrome`
      (depends on T025)

**Checkpoint**: Column 3 is fully functional and independently testable; Columns 1-4
together already satisfy most of spec FR-008's capability list.

---

## Phase 7: User Story 5 - Set duration, calculate, and see the price in one panel (Priority: P1) 🎯

**Goal**: Column 5 holds the duration selector, Calculate action, and full result.

**Independent Test**: `quickstart.md` Scenario 7.

- [ ] T027 [US5] Build `frontend/src/components/workspace/PricingPanel.tsx`: duration
      `select`, Calculate `button`, and the total price/warnings/unpriceable-items result,
      using shadcn primitives, consuming state/callbacks from `WorkspacePage`
- [ ] T028 [US5] Mount `PricingPanel` as column 5 in `WorkspacePage.tsx` (depends on T027)
- [ ] T029 [US5] Live-verify `quickstart.md` Scenario 7 via `claude-in-chrome` (depends on
      T028)

**Checkpoint**: All five columns are functional — every capability from spec FR-008 is
reachable somewhere in the new layout (SC-002).

---

## Phase 8: User Story 6 - A single, consistent visual design across every panel (Priority: P2)

**Goal**: Tailwind/shadcn/ui/Lucide applied consistently across all five panels, with the
diagram-internals exception intact.

**Independent Test**: `quickstart.md` Scenario 8.

- [ ] T030 [P] [US6] Restyle `frontend/src/components/CatalogSearchPanel.tsx`,
      `PricingInputsForm.tsx`, `SkuDetail.tsx`, `DataConnectorPanel.tsx`,
      `ConfirmDeleteDialog.tsx`, and `ErrorMessage.tsx` internally with Tailwind
      utilities/shadcn primitives — no prop or behavior changes; every existing test for
      these components keeps passing unchanged
- [ ] T031 [US6] Add Lucide icons to common actions across all five panels — add,
      remove/delete, connect, edit, search, calculate, warning/error (FR-010)
- [ ] T032 [US6] Confirm the diagram's own node/edge rendering (`ArchitectureDiagramPanel`'s
      canvas internals, T015) is the documented exception (FR-009/SC-004) — verify only the
      surrounding panel chrome (border, empty state, buttons) needs the design-system pass,
      not the node/edge markup itself
- [ ] T033 [US6] Live-verify `quickstart.md` Scenario 8 via `claude-in-chrome` (depends on
      T030, T031, T032)

**Checkpoint**: All six user stories complete — every acceptance scenario in `spec.md` is
satisfied.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Confirm no regressions across the existing frontend test/build/type-check
suite, and do a final combined live pass.

- [ ] T034 [P] Run the full frontend test suite (`npm test` in `frontend/`) and confirm all
      existing tests (unchanged contracts, per T030) plus T005's new tests pass
- [ ] T035 [P] Run `npm run build` and `npm run check-api-types` in `frontend/`; confirm a
      clean build and zero API-contract drift (no backend touched, per Assumptions)
- [ ] T036 Run all nine `quickstart.md` scenarios together as a final combined end-to-end
      check, including Scenario 9's empty-state/deletion-reset edge cases and a walk-through
      of SC-001-004 (depends on T014, T018, T022, T026, T029, T033)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (every panel is
  rendered from the `WorkspacePage` shell this phase builds).
- **User Story 1 (Phase 3)**: Depends only on Foundational — can proceed independently of
  Phases 4-7.
- **User Story 4 (Phase 4)**: Depends only on Foundational.
- **User Story 2 (Phase 5)**: Depends on Foundational and on User Story 4's `onEdgeClick`
  relocation (T020 reads T015's work) — otherwise independent of Phase 3.
- **User Story 3 (Phase 6)**: Depends on User Story 4 (the per-service click target it
  displays the result of) and User Story 2 (the search-pick wiring it also displays the
  result of).
- **User Story 5 (Phase 7)**: Depends only on Foundational — can proceed independently of
  every other user story.
- **User Story 6 (Phase 8)**: Depends on User Stories 1-5 all being built (it restyles their
  finished markup).
- **Polish (Phase 9)**: Depends on all six user stories being complete.

### Parallel Opportunities

- T003 and T004 can run in parallel (independent installs).
- T005 can be written in parallel with T007/T008 (different files, no dependency until T009
  needs T006).
- User Story 1 (Phase 3) and User Story 5 (Phase 7) have no dependency on each other or on
  User Stories 2/3/4 beyond Foundational — either can be built in parallel with the
  US4→US2→US3 chain if staffed.
- T030 (US6's restyle pass) can start in parallel across its six listed files.
- T034 and T035 can run in parallel once all six user stories are complete.

---

## Parallel Example: Setup + Foundational Kickoff

```bash
# Independent installs, launched together:
Task: "Install lucide-react in frontend/package.json"
Task: "Add shadcn/ui primitives via CLI into frontend/src/components/ui/"

# Once T002 is in, T005 (tests) and T007/T008 (shell + routing) can proceed in parallel:
Task: "Write tests-first for ServiceConfigSelection in frontend/tests/unit/serviceConfigSelection.test.ts"
Task: "Create the five-column shell in frontend/src/pages/WorkspacePage.tsx"
```

---

## Implementation Strategy

### MVP First (Through User Story 4)

1. Complete Setup + Foundational (T001-T010) — the shell exists but is empty.
2. Complete User Story 1 (T011-T014) — Architecture selection works.
3. Complete User Story 4 (T015-T018) — the diagram is back and interactive, with its new
   per-service click target.
4. **STOP and VALIDATE**: at this point the app is usable for viewing (not yet editing)
   Architectures in the new layout.

### Incremental Delivery

1. Setup + Foundational → empty shell builds and runs.
2. User Story 1 → validate → Architecture selection works.
3. User Story 4 → validate → diagram works, new click target ready.
4. User Story 2 → validate → Collections/Connectors/search work.
5. User Story 3 → validate → service configuration works — the app is now fully
   feature-complete relative to today's application (SC-002).
6. User Story 5 → validate → pricing works (independent of 2-4, could land anytime after
   Foundational).
7. User Story 6 → validate → the visual-design-system pass is complete.
8. Phase 9 polish → confirm no regressions.

## Notes

- [P] tasks = different files, no dependency.
- [Story] label maps task to specific user story for traceability.
- Verify T005's tests fail before T006 makes them pass (TDD, Constitution Principle V — the
  one piece of this feature that is genuinely extractable logic, not presentation).
- Commit after each task or logical group, per this project's established
  `/speckit-git-commit` cadence.
