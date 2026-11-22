# Tasks: Deferred UI and Admin Fixes

**Input**: Design documents from `specs/027-deferred-ui-admin-fixes/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: included. Constitution V makes the preferences rule and the icon check test-first;
every acceptance scenario and success criterion maps to a test or a `[MANUAL]` item (see
[Coverage](#coverage)).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to (US1–US5)

---

## Phase 1: Setup

- [ ] T001 Add `@axe-core/playwright` as a dev dependency in `frontend/package.json` (exact version, `npm install` updates `frontend/package-lock.json`)

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: identity changes must reset everything identity-scoped, and both header menus need
the shared menu wrapper. US1, US2 and US3 depend on this phase; US4 and US5 don't.

- [ ] T002 Write `frontend/tests/unit/preferences.test.ts` cases (extend the existing file): `preferencesStore.reset()` drops loaded values and pending saves, notifies listeners, and the next `load()` fetches again
- [ ] T003 Implement `reset()` in `PreferencesStore` in `frontend/src/lib/preferences.ts`, and an `onIdentityChanged()` helper in `frontend/src/lib/identity.ts` (new) that resets the store, clears the TanStack Query cache (`queryClient.clear()`) and reloads preferences; call it from today's login success in `frontend/src/components/layout/IdentityMenu.tsx` in place of the two `invalidateQueries` calls
- [ ] T004 [P] Write `frontend/tests/unit/HeaderMenu.test.tsx` (contracts/user-menu-ui.md "Keyboard"): Enter, Space and ArrowDown on the trigger open the menu and focus the first item; ArrowDown / ArrowUp move between items and wrap; Escape closes and returns focus to the trigger; an `onEscapeKeyDown` that calls `preventDefault` keeps it open; `aria-expanded` follows the state
- [ ] T005 Implement `frontend/src/components/layout/HeaderMenu.tsx` (research R1): Radix `Popover` with a header trigger (`HEADER_CONTROL`, `aria-expanded:bg-header-accent`), Escape → focus the trigger (moved from `TopTabs.tsx`'s `closedByEscape`), ArrowDown on the trigger opens, ArrowUp/ArrowDown move between elements marked `data-menu-item`, and pass-through `onEscapeKeyDown`, `align` and content class
- [ ] T006 Move the Cloud Pricing chevron in `frontend/src/components/layout/TopTabs.tsx` onto `HeaderMenu` (keeping the name-field Escape rule through `onEscapeKeyDown`), mark the provider buttons in `frontend/src/components/layout/ArchitectureMenu.tsx` with `data-menu-item`, and extend `frontend/tests/unit/ArchitectureMenu.test.tsx` with ArrowDown-to-open and ArrowUp/ArrowDown between providers; existing ArrowRight/ArrowLeft tests still pass

**Checkpoint**: one menu behaviour; identity changes reset the client.

---

## Phase 3: User Story 1 - The user menu (Priority: P1) 🎯 MVP

**Goal**: the person icon opens a menu with the name or Guest, Log in or Log out, and Settings
with Colour theme, behaving like the Cloud Pricing menu.

**Independent Test**: as a guest and as a user, open the menu and check its items; operate it
from the keyboard.

### Tests for User Story 1

- [ ] T007 [P] [US1] Write `frontend/tests/unit/UserMenu.test.tsx`: for a guest the menu shows the label "Guest", **Log in**, a Settings heading and **Colour theme: Dark**, and no Log out or Change user (US1-1); for a user it shows the username, **Log out** and Colour theme, and no Log in or Change user (US1-2); the label isn't focusable; **Log in** closes the menu and opens `LoginDialog` (US1-5); the trigger's accessible name is "User menu: Guest" / "User menu: <username>"
- [ ] T008 [P] [US1] Write `frontend/e2e/user-menu.spec.ts`: both header menus from the keyboard only (open with Enter, Space and ArrowDown; ArrowDown/ArrowUp; Escape returns focus to each trigger) (US1-3); log in from the user menu with the seeded test user and see the username (US1-5); with reduced motion emulated, the open menu has no animation and switching the theme has no transition (spec edge case)

### Implementation for User Story 1

- [ ] T009 [US1] Implement `frontend/src/components/layout/UserMenu.tsx` on `HeaderMenu` per contracts/user-menu-ui.md (items in order; Settings section; Log in opens the existing `LoginDialog`, success calls `onIdentityChanged()` and navigates to `/`); until US2 and US3, the Settings heading is shown with no items and Log out is not rendered; T020 adds Colour theme and T025 adds Log out
- [ ] T010 [US1] Replace `IdentityMenu` with `UserMenu` in `frontend/src/components/layout/TopTabs.tsx` and delete `frontend/src/components/layout/IdentityMenu.tsx`; update any test or e2e step that opens the old identity dialog

**Checkpoint**: the user menu works for Log in; US1 is testable on its own.

---

## Phase 4: User Story 2 - Switch between the light and dark themes (Priority: P1)

**Goal**: Colour theme switches the whole app at once; saved for logged-in users only.

**Independent Test**: switch to dark; reload as a user (dark) and as a guest (light).

### Tests for User Story 2

- [ ] T011 [P] [US2] Extend `backend/tests/contract/test_preferences.py` per contracts/preferences-api.md: a logged-in user saves and reads `appearance.theme` dark and clears it with null; a guest's patch with `appearance` is 403 `theme_not_saved_for_guests` and saves nothing (including the other sections in the same patch); an unknown theme or extra key is 422; patches without `appearance` are unchanged (FR-005)
- [ ] T012 [P] [US2] Write `frontend/tests/unit/theme.test.ts`: `applyTheme` toggles `.dark` on `document.documentElement` (US2-1); `setTheme` for a logged-in user patches `appearance` and writes the cache `{user_id, theme}`; for a guest it patches nothing and writes no cache (US2-3); with no saved theme the app is light (US2-4); the pre-paint snippet applies dark only when the cache's `user_id` equals the current identity; a failed save keeps the theme applied (edge case)
- [ ] T013 [P] [US2] Write `frontend/e2e/theme.spec.ts`: as a logged-in user, pick Dark → `html.dark` with no navigation and the item reads "Colour theme: Light"; reload → still dark; log in in a second browser context → dark (US2-2); as a guest, pick Dark, reload → light (US2-3); a fresh browser → light (US2-4); time from click to `html.dark` under 1 s (SC-001)
- [ ] T014 [P] [US2] Write `frontend/e2e/contrast.spec.ts` (research R4): `@axe-core/playwright` with only the `color-contrast` rule, in light and dark, on the workspace with an architecture open, the Agent tab with a Results pane (scripted provider, as `agent.spec.ts` does), Trends, Admin, an open dialog, and both open header menus; zero violations (FR-007, SC-002)
- [ ] T015 [P] [US2] Extend `frontend/tests/unit/theme.contrast.test.ts` with any colour token pairs used by the agent UI (023–026) and the new menu that it doesn't check yet

### Implementation for User Story 2

- [ ] T016 [US2] Add `Appearance` (`theme: Literal["light", "dark"]`, strict) and `appearance` to `Preferences` and `PreferencesPatch` in `backend/src/models/schemas.py`; refuse a patch with `appearance` from a user without a username in `backend/src/api/preferences.py` (403, before saving anything); regenerate `frontend/src/api/generated/schema.d.ts` with `npm run generate-api-types`
- [ ] T017 [US2] Add the `appearance` section to `frontend/src/lib/preferences.ts` (`SectionValues`, `withSection`, `patchBody`)
- [ ] T018 [US2] Implement `frontend/src/lib/theme.ts` (research R2, R3): `applyTheme`, `setTheme(theme, {loggedIn, userId})`, the cache read/write/clear, and a `useTheme()` hook that applies the account's theme once preferences load and clears the cache for a guest identity
- [ ] T019 [US2] Add the pre-paint inline script to `frontend/index.html` (reads `cloud-pricing-theme` and `cloud-pricing-current-identity-id`; adds `dark` to `<html>` only when they match; wrapped in try/catch)
- [ ] T020 [US2] Wire Colour theme in `frontend/src/components/layout/UserMenu.tsx` to `useTheme()` (the menu stays open on the item, which now offers the other theme); fix any element T014 or T015 reports, in `frontend/src/index.css` or the component that bypasses the tokens

**Checkpoint**: the theme works end to end; US2-6 is checked by hand in quickstart section 3.

---

## Phase 5: User Story 3 - A logged-in user logs out (Priority: P2)

**Goal**: Log out returns the browser to its earlier guest, or a new one.

**Independent Test**: as a guest create an architecture, log in, log out: Guest and the guest's
architecture are back.

### Tests for User Story 3

- [ ] T021 [P] [US3] Write `frontend/tests/unit/logOut.test.ts` for `api.logOut()` in `frontend/src/api/client.ts`: the current identity becomes the stored guest ID (US3-1); with no guest ID stored, a new one is created and used (US3-4); the guest ID key is never overwritten
- [ ] T022 [P] [US3] Extend `frontend/tests/unit/UserMenu.test.tsx`: Log out with no unsaved work calls `api.logOut()`, removes the theme cache and `.dark`, calls `onIdentityChanged()` and navigates to `/`; with unsaved work it shows `UnsavedWorkDialog` first and Cancel keeps the user logged in (FR-011)
- [ ] T023 [P] [US3] Extend `frontend/e2e/user-menu.spec.ts`: as a guest create an architecture; log in (the user's own architectures list, theme dark); Log out → menu shows Guest and Log in, the guest's architecture is listed again, the user's are not, the theme is light, and the Agent tab shows its guest message (US3-1 to US3-3, SC-004); clear `cloud-pricing-guest-id` while logged in, then Log out → a new guest with no architectures (US3-4); with a pending agent proposal, Log out, log back in: the proposal is still pending and nothing was saved (spec edge case)

### Implementation for User Story 3

- [ ] T024 [US3] Implement `logOut()` in `frontend/src/api/client.ts` (research R5: `setCurrentIdentityId(getGuestId())`)
- [ ] T025 [US3] Wire Log out in `frontend/src/components/layout/UserMenu.tsx`: the unsaved-work check with the existing `UnsavedWorkDialog` (`frontend/src/components/workspace/UnsavedWorkDialog.tsx`, `unsavedWork` from `frontend/src/lib/unsavedWork.ts`), then `api.logOut()`, the theme reset, `onIdentityChanged()` and `navigate("/")`

**Checkpoint**: Log out works; US1–US3 complete.

---

## Phase 6: User Story 4 - The Admin sees each provider's Trends history status (Priority: P2)

**Goal**: System Information shows each provider's history state.

**Independent Test**: System Information with providers in each state shows each one.

### Tests for User Story 4

- [ ] T026 [P] [US4] Extend `backend/tests/contract/test_admin_system_info.py`: a provider whose history state file can't be read gets `history: null` and the rest of the response is intact (FR-013)
- [ ] T027 [P] [US4] Extend `frontend/tests/unit/SystemInformationSection.test.tsx`: Complete (weeks built and last built date) (US4-1); "N weeks missing" (US4-2); Building and "Failed: <error>" (US4-3); "No history yet" for `weeks_total` 0, not zeros (US4-4); "Unavailable" for null; Check now and the minute refresh re-render it from the new response (US4-5)

### Implementation for User Story 4

- [ ] T028 [US4] Make `history` nullable in `ProviderSystemOut` in `backend/src/models/schemas.py`, and catch the read error in `_history_out` in `backend/src/api/admin_system.py` (log it once, return None); regenerate the frontend API types
- [ ] T029 [US4] Add the Trends history cell to the provider rows in `frontend/src/components/admin/SystemInformationSection.tsx` per data-model.md §3 (shown state in order of precedence)

**Checkpoint**: US4 complete on its own.

---

## Phase 7: User Story 5 - The Admin is told about GCP and Azure services with no icon (Priority: P3)

**Goal**: first-party GCP and Azure services with no canvas icon appear in the Issues table, with
one Marketplace count line per provider.

**Independent Test**: with the GCP and Azure fixtures, the Issues table lists their first-party
services without icons and the Marketplace count.

### Tests for User Story 5

- [ ] T030 [P] [US5] Extend `backend/tests/unit/test_icon_map_consistency.py`: `gcp_service_icons.json` and `azure_service_icons.json` have the same `by_id` and `overrides` as `frontend/src/lib/{gcp,azure}ServiceIcons.generated.ts`; every overridden ID also has a `by_id` entry (FR-015, research R7)
- [ ] T031 [P] [US5] Extend `backend/tests/unit/test_icon_coverage.py` with GCP and Azure snapshots built in the test (as the AWS tests do): a first-party service with no icon is a `missing_icon` issue with `provider` (US5-1); one missing from the previous snapshot is `is_new` (US5-2); a service in `by_id` is not reported, so issues equal the IDs the canvas resolves to fallback (US5-3, SC-006); Marketplace and third-party services give one `marketplace_without_icons` issue with their `count` and are not listed (US5-4); no active snapshot gives no issues (FR-016); AWS results are unchanged
- [ ] T032 [P] [US5] Extend `backend/tests/contract/test_admin_system_info.py`: every issue has `provider`; the top-level `issues` hold all providers' issues, AWS, then GCP, then Azure
- [ ] T033 [P] [US5] Extend `frontend/tests/unit/SystemInformationSection.test.tsx`: the Issues table has a Provider column; a `marketplace_without_icons` row shows its message

### Implementation for User Story 5

- [ ] T034 [US5] Extend `backend/scripts/generate_provider_service_icon_map.py` to also write `backend/src/pricing_data/{gcp,azure}_service_icons.json` (data-model.md §5) from the same mapping, and move `read_services` (and the `Service` record, `_GCP_THIRD_PARTY`) into `backend/src/pricing_data/provider_services.py` so the server and the script share it; update `backend/tests/unit/test_provider_icon_generator.py` for the move
- [ ] T035 [US5] Run the generator for GCP and Azure on the newest local snapshots and `../images-web/` (quickstart section 2), refreshing the `.generated.ts` maps and `frontend/src/assets/{gcp,azure}-icons/` from 020's 2026-11-02 run (clarification 2026-11-22) and writing the two JSON files; check the report (no categorized service without an icon; added and dropped icons are real name matches); a second run changes nothing; record here the icons added and dropped per provider; commit the maps, icons and JSON together
- [ ] T036 [US5] Make `backend/src/pricing_data/icon_coverage.py` provider-aware (research R7): the map per provider, services from `provider_services.read_services` for GCP and Azure, the first-party filter and the Marketplace count issue, the provider's fallback in the message; add `provider` and `count` to `Issue` in `backend/src/pricing_data/active_snapshot.py`
- [ ] T037 [US5] Run the analysis for every provider after its active snapshot changes, in `backend/src/pricing_data/active_snapshot.py` (today only AWS), with `_previous` taking the provider
- [ ] T038 [US5] Add `provider`, the `marketplace_without_icons` kind and `count` to `IssueOut`, and return every provider's issues in the top-level `issues`, in `backend/src/models/schemas.py` and `backend/src/api/admin_system.py`; regenerate the frontend API types
- [ ] T039 [US5] Add the Provider column and the summary row to the Issues table in `frontend/src/components/admin/SystemInformationSection.tsx`

**Checkpoint**: all five stories complete.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T040 [P] Update `docs/features/workspace-and-preferences.md` (header user menu, Colour theme, the theme in "Settings saved to your account" for logged-in users only, both menus' keyboard), `docs/features/accounts-and-sharing.md` (user menu, Log out, no Change user) and `docs/features/admin.md` (Trends history status, Issues for GCP and Azure, Provider column); remove the "planned" / "not shown yet" notes these replace
- [ ] T041 [P] Add the 027 line to `CHANGELOG.md` under Unreleased (user menu with Log out and Colour theme; Trends history status and GCP and Azure icon issues on the Admin page; GCP and Azure canvas icons refreshed to the current price lists)
- [ ] T042 Run the whole backend suite, ruff on touched files, frontend unit tests, type-check, lint and build, and the whole e2e suite; record the results in this file; time the icon check for GCP and Azure on the real local snapshots and record it (plan: under 1 s)
- [ ] T043 Run the quickstart manual walk-through with the user (section 3, the two `[MANUAL]` items) and record what was checked

---

## Dependencies & Execution Order

- **Setup (T001)** → only T014 needs it.
- **Foundational (T002–T006)** blocks US1, US2 and US3. T002 → T003; T004 → T005 → T006.
- **US1 (T007–T010)** after Foundational. **US2** and **US3** need US1's `UserMenu` (T009) for
  their menu items; their backend and library parts (T011, T016–T019, T021, T024) can start
  after Foundational.
- **US4 (T026–T029)** and **US5 (T030–T039)** are independent of everything else and of each
  other, except that both edit `SystemInformationSection.tsx` and `schemas.py` (do T029 and
  T039, T028 and T038, one after the other).
- Within US5: T034 → T035 → T036 → T037 → T038 → T039; tests T030–T033 first.
- **Polish** after all stories.

### Parallel opportunities

- T004 with T002–T003.
- US1 tests T007 and T008 together.
- US2 tests T011–T015 together; T016 (backend) with T018–T019 (frontend).
- US3 tests T021–T023 together.
- US4 and US5 can run alongside US1–US3; their tests T026–T027 and T030–T033 together.
- T040 and T041 together.

### Parallel example: User Story 2

```text
T011 backend/tests/contract/test_preferences.py
T012 frontend/tests/unit/theme.test.ts
T013 frontend/e2e/theme.spec.ts
T014 frontend/e2e/contrast.spec.ts
T015 frontend/tests/unit/theme.contrast.test.ts
```

## Implementation Strategy

- **MVP**: Setup, Foundational and US1 (the menu with Log in), then US2 (the theme), the two P1
  stories.
- **Then**: US3 (Log out), US4 (history status), US5 (icon issues), each shippable on its own.
- Each story ends at a checkpoint where its tests pass.

## Coverage

Each acceptance scenario and success criterion maps to a test, or is `[MANUAL]` in quickstart.md
section 3 (constitution 1.3.0, Principle V).

| Scenario or criterion | Covered by |
|---|---|
| US1-1 guest's menu items | T007 `UserMenu.test.tsx` |
| US1-2 user's menu items, no Change user | T007 |
| US1-3 both menus from the keyboard | T004 `HeaderMenu.test.tsx`; T006 `ArchitectureMenu.test.tsx`; T008 `e2e/user-menu.spec.ts` |
| US1-4 the menus look alike | `[MANUAL]` quickstart 3.1 |
| US1-5 Log in starts today's flow | T007; T008 |
| US2-1 switch at once, item flips | T012 `theme.test.ts`; T013 `e2e/theme.spec.ts` |
| US2-2 user's theme persists across reloads and browsers | T011 `test_preferences.py`; T013 |
| US2-3 guest's theme not saved | T011 (server refuses); T012; T013 |
| US2-4 light by default | T012; T013 |
| US2-5 WCAG AA contrast on every page in both themes | T014 `e2e/contrast.spec.ts`; T015 `theme.contrast.test.ts` |
| US2-6 legibility on real data | `[MANUAL]` quickstart 3.2 |
| US3-1 back to the earlier guest | T021 `logOut.test.ts`; T023 |
| US3-2 nothing of the user's remains | T022; T023 |
| US3-3 the guest's architectures again | T023 |
| US3-4 no earlier guest → new guest | T021; T023 |
| US4-1 to US4-5 history states and refresh | T027 `SystemInformationSection.test.tsx`; T026 (unreadable state) |
| US5-1, US5-2 first-party issues with provider, "new" rule | T031 `test_icon_coverage.py`; T032; T033 |
| US5-3 table and canvas agree | T030 `test_icon_map_consistency.py`; T031 |
| US5-4 one Marketplace count line | T031; T033 |
| Edge: theme save fails | T012 |
| Edge: unsaved work before Log out | T022 |
| Edge: reduced motion | T008 |
| Edge: pending agent proposal at Log out | T023 |
| Edge: unreadable history | T026; T027 |
| Edge: no snapshot → no icon issues | T031 |
| SC-001 two clicks, under 1 s | T013 |
| SC-002 contrast | T014; T015 |
| SC-003 user's theme applied, guest's never | T011; T013 |
| SC-004 Log out cases | T021; T023 |
| SC-005 Admin can tell each history state | T027 |
| SC-006 Issues table matches the canvas | T030; T031 |
