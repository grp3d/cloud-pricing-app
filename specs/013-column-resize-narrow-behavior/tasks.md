---

description: "Task list for Architecture Panel Narrow-Width Layout (013-column-resize-narrow-behavior)"
---

# Tasks: Architecture Panel Narrow-Width Layout

**Input**: Design documents from `/specs/013-column-resize-narrow-behavior/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md (all present; no `contracts/` — no API changes)

**Tests**: Included. `plan.md`'s Technical Context and Structure Decision commit to a new
`ProviderArchitecturePanel.test.tsx`, and Constitution Principle V permits tests-after (not
test-first) for this UI-only presentational change — tests are written alongside/after each
story's implementation, not required to fail first.

**Organization**: Tasks are grouped by user story from `spec.md` (US1/US2/US3, priorities
P1/P1/P2). All work lands in exactly two files
(`frontend/src/components/workspace/ProviderArchitecturePanel.tsx` and its new sibling test
file), so parallelism across tasks is limited — see **Parallel Opportunities** below.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Existing web app: `frontend/src/...` for this feature (no `backend/` changes). All paths
below are relative to the repository root.

---

## Phase 1: Setup

**Purpose**: Confirm a clean baseline before touching the component.

- [ ] T001 Run `cd frontend && npm run lint && npm test` to confirm the existing suite is
  green before any edits (baseline for comparison once this feature's changes land).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the shared test scaffold once, since all three user stories below add
tests to the same new file.

**⚠️ CRITICAL**: Complete this before starting any user story's test task.

- [ ] T002 Create `frontend/src/components/workspace/ProviderArchitecturePanel.test.tsx`
  with: the necessary imports (`render`, `screen`, `vi` from vitest/RTL, `Tooltip`
  provider wrapper if the existing `Tooltip` components require one — check how other
  component tests in `frontend/src/components/**/*.test.tsx` wrap tooltip-using
  components, if any exist, for the established pattern), and a `renderPanel(overrides)`
  helper that supplies all required `ProviderArchitecturePanelProps` (a `providers` array
  with one active provider, an `architectures` array containing at least one entry with a
  long `name` — e.g. 60+ characters — so wrap behavior is observable, `isGuest: false` so
  both share and delete buttons render, all callback props as `vi.fn()`, and a `width`
  prop that defaults to `250` but can be overridden per test, e.g. to `56` to simulate the
  panel's minimum resizable width).

**Checkpoint**: Foundation ready — user story tests/implementation can now proceed.

---

## Phase 3: User Story 1 - Create form shrinks instead of losing its button (Priority: P1) 🎯 MVP

**Goal**: The "New Architecture" name input shrinks first as the panel narrows; the Create
button is never clipped, scrolled out of view, or hidden — at the panel's minimum resizable
width it may wrap onto its own line below the input, but it always stays fully visible and
clickable.

**Independent Test**: Render the panel at `width=56` (the minimum) and confirm the Create
button (`getByRole("button", { name: "Create" })`) is present in the DOM and not clipped,
while the name input is also present and narrower than at the default width.

### Tests for User Story 1

- [ ] T003 [US1] In `frontend/src/components/workspace/ProviderArchitecturePanel.test.tsx`,
  add a test that renders via `renderPanel({ width: 56 })` and asserts
  `screen.getByRole("button", { name: "Create" })` is present and enabled, and
  `screen.getByPlaceholderText("New Architecture name")` is also present (both controls
  exist simultaneously at the minimum width — neither is removed from the DOM).

### Implementation for User Story 1

- [ ] T004 [US1] In
  `frontend/src/components/workspace/ProviderArchitecturePanel.tsx`, update the
  create-form `<form>` element (currently `className="mt-1 flex gap-1"`, around line 277)
  to `className="mt-1 flex flex-wrap gap-1"` so the Create button can wrap onto its own
  line instead of overflowing when the input has hit its minimum width.
- [ ] T005 [US1] In the same file, update the name `<input>` element (currently
  `className="min-w-0 flex-1 rounded border border-border bg-background px-1.5 py-1
  text-2xs"`, around line 284-285) by replacing `min-w-0` with `min-w-[3rem]` so the input
  always keeps a small but visible, usable width instead of shrinking all the way to zero
  before the row wraps.

**Checkpoint**: User Story 1 is independently functional — verify with `npm test -- ProviderArchitecturePanel` and the manual step in `quickstart.md` step 5 (Create button bullet).

---

## Phase 4: User Story 2 - Action buttons stay visible while narrowing (Priority: P1)

**Goal**: The import button and each listed architecture's share/delete buttons remain
fully visible and clickable at every panel width down to the minimum resizable width — the
architecture name area yields space (and, at the extreme end, wraps to its own line) before
any action button is affected.

**Independent Test**: Render the panel at `width=56` with at least one architecture
(`isGuest: false`) and confirm the import button and that architecture's share and delete
buttons are all present in the DOM.

**Note on ordering**: This story's guarantee for the per-row share/delete buttons is only
complete once User Story 3's `min-w-0` change to the name button (T009) has also landed —
both T007 below and T009 touch the same list-item block. Implement T009 before or together
with T007, even though this story is prioritized above User Story 3; they are still
independently *testable* (T006's test can be written now and will pass once both changes
are in place), just not fully independently *implementable* in isolation from T009.

### Tests for User Story 2

- [ ] T006 [US2] In
  `frontend/src/components/workspace/ProviderArchitecturePanel.test.tsx`, add a test that
  renders via `renderPanel({ width: 56 })` with `isGuest: false` and at least one
  architecture, and asserts the import button
  (`screen.getByRole("button", { name: "Import an architecture" })`), the share button for
  that architecture (`screen.getByRole("button", { name: /Make .* (public|private)/ })`),
  and its delete button (`screen.getByRole("button", { name: /Delete /  })`) are all
  present in the DOM.

### Implementation for User Story 2

- [ ] T007 [US2] In
  `frontend/src/components/workspace/ProviderArchitecturePanel.tsx`, update the
  per-architecture `<li>` element in the expanded-row branch (currently
  `className="flex items-center gap-1"`, around line 201) to
  `className="flex flex-wrap items-start gap-1"` so the share/delete icon buttons wrap onto
  their own line if the row's minimum content width (icon buttons + name) exceeds the
  panel's available width, instead of being clipped by the ancestor `<aside>`'s
  `overflow-hidden` or scrolled out of the `ScrollArea` viewport.

**Checkpoint**: User Stories 1 AND 2 both work — verify with `npm test -- ProviderArchitecturePanel` and `quickstart.md` step 5 (import/share/delete bullets).

---

## Phase 5: User Story 3 - Architecture names word-wrap instead of truncating (Priority: P2)

**Goal**: Architecture names that don't fit on one line wrap across multiple lines (like
the "AWS Architectures" heading already does) instead of being truncated with an ellipsis.

**Independent Test**: Render the panel with a long-named architecture at a narrow width and
confirm the full name text is present in the DOM (no ellipsis character, and the name
button's className no longer includes `truncate`).

### Tests for User Story 3

- [ ] T008 [US3] In
  `frontend/src/components/workspace/ProviderArchitecturePanel.test.tsx`, add a test that
  renders via `renderPanel({ width: 56 })` with an architecture whose `name` is a long
  string (e.g. 60+ characters) and asserts: (a) `screen.getByText(longName)` finds the full
  name text in the DOM, and (b) the rendered name button element does not have the
  `truncate` class (query via `screen.getByRole("button", { name: longName })` and check
  `element.className` does not include `"truncate"`).

### Implementation for User Story 3

- [ ] T009 [US3] In
  `frontend/src/components/workspace/ProviderArchitecturePanel.tsx`, update the
  architecture-name `<Button>` element in the expanded-row branch (currently
  `className="flex-1 justify-start truncate"`, around line 202-207) to
  `className="min-w-0 flex-1 justify-start whitespace-normal break-words text-left"` —
  removing `truncate`, adding `min-w-0` (so the button can still shrink for flex purposes
  now that `truncate`'s implicit `overflow-hidden` minimum-width behavior is gone),
  `whitespace-normal` (to override the shared `Button` component's base
  `whitespace-nowrap`), `break-words` (to wrap very long unbroken names), and `text-left`
  (multi-line text should stay left-aligned, matching the single-line default).

**Checkpoint**: All three user stories are independently functional — verify with `npm test -- ProviderArchitecturePanel` and the full `quickstart.md` manual walkthrough.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final verification across all three stories together.

- [ ] T010 Run `cd frontend && npm run lint && npm test` and confirm the whole suite
  (including the new `ProviderArchitecturePanel.test.tsx`) passes with no regressions.
- [ ] T011 Manually run through `specs/013-column-resize-narrow-behavior/quickstart.md`
  end-to-end in a real browser (drag column 1 from its default width down to the minimum
  and back), confirming every check in its step 5 and step 6 (collapse/expand still
  unaffected) holds.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — run first.
- **Foundational (Phase 2)**: Depends on Setup; creates the shared test file used by all
  three stories — BLOCKS all user story test tasks (T003, T006, T008).
- **User Stories (Phase 3-5)**: All depend on Foundational (T002). Implementation tasks
  within a story do not depend on other stories' implementation tasks being *complete*,
  except as noted below.
- **Polish (Phase 6)**: Depends on all three user stories being implemented.

### Cross-Story Dependency (exception to normal independence)

- **T007 (US2) depends on T009 (US3)** landing first (or simultaneously): US2's guarantee
  that share/delete icon buttons never get clipped relies on the name button having
  `min-w-0` (added in T009) so it can shrink to make room; without T009, T007's
  `flex-wrap` alone still works but the name button may resist shrinking below its
  text's natural width, reducing how much of the row's overflow `flex-wrap` actually
  needs to absorb. Implement in this order: **T004, T005 (US1) → T009 (US3) → T007
  (US2)**, even though US1/US2 are the higher-priority (P1) stories — their tests (T003,
  T006, T008) can still be written at any point, since they describe the desired end
  state.

### Within Each User Story

- Test task before implementation task is written first in this document for reference,
  but per the Constitution's UI exception, implementation may proceed without waiting for
  the test to fail first — write both together.

### Parallel Opportunities

This feature has limited parallelism: every task edits one of just two files
(`ProviderArchitecturePanel.tsx` or its new test file), so no `[P]` markers are used.
Tasks within a phase should be done sequentially to avoid clobbering each other's edits.
The only true parallel opportunity is running Phase 1's lint/test baseline (T001)
independently before any edits begin.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002)
3. Complete Phase 3: User Story 1 (T003-T005)
4. **STOP and VALIDATE**: Confirm the Create button never disappears while narrowing,
   even though action-button and name-wrap fixes aren't in yet.

### Incremental Delivery

1. Setup + Foundational → test scaffold ready (T001-T002)
2. User Story 1 → Create button never hidden (T003-T005) — MVP
3. User Story 3 → names wrap instead of truncating, which also unblocks User Story 2's
   full guarantee (T008-T009)
4. User Story 2 → import/share/delete buttons verified to never clip (T006-T007)
5. Polish → full regression pass + manual quickstart walkthrough (T010-T011)
