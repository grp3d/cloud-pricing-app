---

description: "Task list for User Accounts, Administration, and Architecture Sharing"
---

# Tasks: User Accounts, Administration, and Architecture Sharing

**Input**: Design documents from `/specs/012-user-accounts-sharing/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md (all present). This feature touches **both** `backend/` and `frontend/` — see plan.md's Technical Context and Project Structure.

**Tests**: Per Constitution Principle V, test-first applies to: password hashing/verification, the `get_current_user`/`require_admin` active/admin checks, all `/admin/users` CRUD (including default-Admin protection and purge cascade), the `is_public` toggle's ownership/guest-owner rejection, the importable-architectures grouping/sorting, and `import_architecture`'s deep-copy/id-remap correctness (all backend Postgres read/write logic for user-defined objects). The tab shell, person icon/login popup, Admin table UI, sharing icon, and Import dialogs are presentational UI, validated live against `quickstart.md` via `claude-in-chrome`, per Principle V's carve-out.

**Organization**: Tasks are grouped by user story, ordered by priority per spec.md: US1, US2 (P1), then US3, US4 (P2), then US5 (P3). Every story depends on the Foundational phase's extended identity model; US4 (import) is most meaningfully demoed once US3 (sharing) has made something public, but its own contract/unit tests can be written and run against seeded data independent of US3's UI.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: `US1`-`US5`, matching spec.md
- File paths are relative to the repository root and follow plan.md's Project Structure

## Phase 1: Setup

**No tasks.** No new dependencies or project scaffolding are needed — this feature extends the existing `backend/` + `frontend/` split with new files inside already-established directories (see Foundational and per-story phases below).

## Phase 2: Foundational

**Purpose**: The extended identity model, auth dependencies, and tab shell every user story needs before it can be meaningfully built or tested — must complete before any user story phase starts.

- [X] T001 [P] Write a failing unit test in `backend/tests/unit/test_auth_service.py` for `hash_password`/`verify_password`: round-trips a password, asserts the stored format `pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>`, asserts a wrong password fails verification, asserts two hashes of the same password differ (distinct salts).
- [X] T002 Implement `hash_password(password: str) -> str` / `verify_password(password: str, stored: str) -> bool` in `backend/src/services/auth_service.py`, per research.md §2 (`hashlib.pbkdf2_hmac` + `secrets.token_hex`, no new dependency). Depends on T001.
- [X] T003 [P] Write a failing integration test in `backend/tests/integration/test_user_seed.py`: after migrations run, exactly one `User` row has `username='Admin', is_admin=True, is_active=True, is_default_admin=True`, and `verify_password("admin123", row.password_hash)` is `True`.
- [X] T004 Create Alembic migration `backend/src/db/migrations/versions/0004_user_accounts_sharing.py`: add `users.username` (nullable `String`, partial unique index `WHERE username IS NOT NULL`), `users.password_hash` (nullable `String`), `users.is_active`/`is_admin`/`is_default_admin` (`Boolean`, defaults `true`/`false`/`false`); add `architectures.is_public` (`Boolean`, default `false`); insert the seeded Admin row (literal `hash_password("admin123")` output baked in at authoring time, per 010's `0003` literal-value precedent) guarded by `WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'Admin')`. Depends on T002, T003.
- [X] T005 [P] Add `username`, `password_hash`, `is_active`, `is_admin`, `is_default_admin` to `User` in `backend/src/models/orm.py`; add `is_public` to `Architecture`.
- [X] T006 Extend `get_current_user` in `backend/src/api/deps.py` to raise `401` when `user.username is not None and not user.is_active` (data-model.md's Auth check — deactivation takes effect on next auth check, FR-008/Edge Cases); add a new `require_admin` dependency (`403` if `not user.is_admin`) built on `CurrentUser`. Depends on T005.
- [X] T007 [P] Write a failing contract test in `backend/tests/contract/test_auth.py` for `GET /auth/me`: a brand-new bearer token still lazily creates a guest row and returns `username: null`; a deactivated named user's next request returns `401` from `get_current_user` itself (not from a route-specific check). Depends on T004, T006.
- [X] T008 Add `CurrentUserOut` to `backend/src/models/schemas.py`; implement `GET /auth/me` in new `backend/src/api/auth.py`; register its router in `backend/src/main.py`. Depends on T005, T006, T007.
- [X] T009 [P] In `frontend/src/api/client.ts`: replace `getUserId()` with `getGuestId()` (the permanent per-browser guest id) and `getCurrentIdentityId()`/`setCurrentIdentityId(id)` (the bearer-token value actually sent, research.md §3); add `getCurrentUser()` calling `GET /auth/me`.
- [X] T010 [P] Create `frontend/src/components/layout/TopTabs.tsx` — "Cloud Pricing" (active, renders the existing route tree), "Trends" (visibly disabled, no route), "Admin" (a link to a new `/admin` route, rendered only when `getCurrentUser().is_admin`). Wire it into `frontend/src/App.tsx` above the existing `<Routes>`, adding the `/admin` route pointed at a placeholder page (filled in by US1's T014). Depends on T009.

**Checkpoint**: Every `User` row can carry a real identity and admin/active flags; `get_current_user`/`require_admin` enforce activity/admin state; the tab shell renders and gates the Admin route. Run `check-api-types` now (Constitution Principle IV) to confirm `CurrentUserOut` regenerates cleanly before any story builds on it.

---

## Phase 3: User Story 1 - Administrator manages user accounts via a role-gated Admin tab (Priority: P1)

**Goal**: The Admin tab's table lets an administrator create users, toggle Active, set/update passwords, and purge a user — with the seeded default Admin account protected from deactivation/purge.

**Independent Test**: quickstart.md Scenario 1.

- [X] T011 [P] [US1] Write failing contract tests in `backend/tests/contract/test_admin_users.py`: `POST /admin/users` creates with `is_active=true`/no password and rejects a duplicate username with `400`; `GET /admin/users` lists only `username IS NOT NULL` rows with a correct `password_hash_suffix`/`has_password`; `PATCH /admin/users/{id}` toggles `is_active` and returns `403` for the default Admin; `PUT /admin/users/{id}/password` sets/updates the hash and its suffix changes; `DELETE /admin/users/{id}` purges the user and cascades to their architectures, returns `403` for the default Admin, and leaves every other user's data intact.
- [X] T012 [US1] Add `AdminUserOut`, `AdminUserCreate`, `AdminPasswordUpdate` to `backend/src/models/schemas.py`; implement `backend/src/api/admin_users.py` (`GET`/`POST /admin/users`, `PATCH /admin/users/{id}`, `PUT /admin/users/{id}/password`, `DELETE /admin/users/{id}`), all behind `require_admin`, with the `is_default_admin` protection check (research.md §7) on the `PATCH` and `DELETE` routes; register the router. Depends on T002, T006, T011.
- [X] T013 [P] [US1] In `frontend/src/api/client.ts`: add `listAdminUsers`, `createAdminUser`, `setAdminUserActive`, `setAdminUserPassword`, `deleteAdminUser`.
- [X] T014 [US1] Build `frontend/src/pages/AdminPage.tsx`: the user table (username, Active checkbox, password Create-or-Update button + popup, purge button + confirmation step), the "Create New User" control, and the default Admin row's disabled Active/purge controls; mount it at the `/admin` route from T010. Depends on T012, T013.
- [X] T015 [US1] Live-verify quickstart.md Scenario 1 via `claude-in-chrome`. Depends on T014.

**Checkpoint**: An administrator can fully create, activate/deactivate, password-manage, and purge user accounts end-to-end, with the default Admin account protected.

---

## Phase 4: User Story 2 - Any user logs in, switches identity, or returns to guest (Priority: P1)

**Goal**: The person icon drives login (create-password-on-first-use or verify-existing-password), safely falls back to guest on any failure, supports "change user," and persists the logged-in identity across reloads/restarts (FR-019a).

**Independent Test**: quickstart.md Scenario 2.

- [X] T016 [P] [US2] Write failing contract tests in `backend/tests/contract/test_auth.py`: `POST /auth/check-username` returns correct `exists`/`has_password` for a nonexistent user, a passwordless user, and a password-set user; `POST /auth/login` returns `401` for a nonexistent username, sets the password and logs in on first use for a passwordless user, succeeds for a correct existing password, returns `401` for a wrong password, and returns `401` for a deactivated user.
- [X] T017 [US2] Add `LoginRequest` to `backend/src/models/schemas.py`; implement `POST /auth/check-username` and `POST /auth/login` in `backend/src/api/auth.py` (contracts/api.md §3 — login sets the password on first use rather than needing a separate "create password" endpoint). Depends on T002, T006, T016.
- [X] T018 [P] [US2] In `frontend/src/api/client.ts`: add `checkUsername(username)` and `login(username, password)` (the latter calling `setCurrentIdentityId` on success).
- [X] T019 [US2] Build `frontend/src/components/auth/LoginDialog.tsx` (username step, then either a "create a password" step or an "enter your password" step per `checkUsername`'s result, reusing `ui/dialog.tsx`) and `frontend/src/components/layout/IdentityMenu.tsx` (top-left person icon: "Guest" + "login", or username + "change user" — both opening `LoginDialog`); mount `IdentityMenu` in the `TopTabs`/`App.tsx` shell from T010. Depends on T017, T018.
- [X] T020 [US2] Live-verify quickstart.md Scenario 2 via `claude-in-chrome`, including a page reload and, if convenient, a full browser restart to confirm FR-019a's persistence. Depends on T019.

**Checkpoint**: Any user can log in, persist their login across a reload/restart, change to a different account, or safely fail back to guest with no error shown.

---

## Phase 5: User Story 3 - Owner marks an architecture public or private (Priority: P2)

**Goal**: A column-1 icon toggles an owned architecture's visibility; guests never see or can use it.

**Independent Test**: quickstart.md Scenario 3.

- [X] T021 [P] [US3] Write failing contract tests extending `backend/tests/contract/test_architectures.py`: `PATCH /architectures/{id}` toggles `is_public` for the owner; returns `403` for a non-owner; returns `403` when the architecture's owner is a guest row (`username IS NULL`).
- [X] T022 [US3] Add `ArchitectureUpdate` to `backend/src/models/schemas.py` and `is_public` to `ArchitectureSummaryOut`; implement `PATCH /architectures/{id}` in `backend/src/api/architectures.py`. Depends on T005, T021.
- [X] T023 [P] [US3] Add `setArchitecturePublic(architectureId, isPublic)` to `frontend/src/api/client.ts`.
- [X] T024 [US3] Add the sharing icon (no border / green border, "Click to make public" / "Click to make private" on hover) next to the delete "✕" in the expanded list item of `frontend/src/components/workspace/ProviderArchitecturePanel.tsx` (`:176-193`), rendered only for a named-user-owned architecture. Depends on T022, T023.
- [X] T025 [US3] Live-verify quickstart.md Scenario 3 via `claude-in-chrome`. Depends on T024.

**Checkpoint**: Any named user can toggle their own architecture's visibility; the control never appears for a guest's architectures.

---

## Phase 6: User Story 4 - A user imports another user's public architecture (Priority: P2)

**Goal**: A column-1 "Import" action lists every other user's public architectures, grouped by owner (Admin first, then alphabetical) and sorted by name within each group; picking one and confirming a name creates an independent copy.

**Independent Test**: quickstart.md Scenario 4.

- [X] T026 [P] [US4] Write a failing unit test in `backend/tests/unit/test_architecture_import.py` for `import_architecture`'s deep-copy graph shape and id-remap correctness — a nested VPC/Application pair's `parent_collection_id` and a `DataConnector`'s `from_collection_id`/`to_collection_id` all point at the *new* cloned rows, not the originals; the copy has no reference back to the source. No mocking, real DB, per this repo's existing test convention.
- [X] T027 [US4] Implement `import_architecture(session, source, new_owner, new_name)` in `backend/src/services/architecture_import.py`, per data-model.md's algorithm. Depends on T005, T026.
- [X] T028 [P] [US4] Write failing contract tests extending `backend/tests/contract/test_architectures.py` for `GET /architectures/importable` (Admin group always first, other groups alphabetical, names sorted within a group, an owner with zero public architectures omitted entirely, the caller's own architectures never included) and `POST /architectures/{id}/import` (`404` for nonexistent/non-public/own-architecture targets; `201` plus an independent copy on success).
- [X] T029 [US4] Implement `GET /architectures/importable` and `POST /architectures/{id}/import` in `backend/src/api/architectures.py`, using T027; add `ImportableArchitecturesOut`/`ArchitectureImportRequest` to `schemas.py`. Depends on T027, T028.
- [X] T030 [P] [US4] Add `listImportableArchitectures()` and `importArchitecture(architectureId, name)` to `frontend/src/api/client.ts`.
- [X] T031 [US4] Build `frontend/src/components/workspace/ImportArchitectureDialog.tsx` (grouped/sorted list, then a naming prompt pre-filled `"My {original name}"`) and wire an "Import" action next to the "AWS Architectures" heading in `ProviderArchitecturePanel.tsx` (`:158-161`), hidden entirely for a guest. Depends on T029, T030.
- [X] T032 [US4] Live-verify quickstart.md Scenario 4 via `claude-in-chrome`. Depends on T031.

**Checkpoint**: Any named user can browse and import any other named user's public architecture as a fully independent copy; guests never see the action.

---

## Phase 7: User Story 5 - Column 1 polish: delete affordance and create-architecture placement (Priority: P3)

**Goal**: The delete "✕" is red with a "Click to remove" hover; the create-architecture control sits under the heading when empty, below the last architecture otherwise.

**Independent Test**: quickstart.md Scenario 5.

- [X] T033 [P] [US5] In `frontend/src/components/workspace/ProviderArchitecturePanel.tsx`, restyle the delete "✕" button (`:185-192`) red and change its tooltip/`aria-label` text to "Click to remove."
- [X] T034 [US5] Confirm the create-architecture control's placement needs no code change: research.md §9 found it already renders after the architecture list (`:215-249`), so it already sits directly under the "AWS Architectures" heading when the list is empty and below the last architecture otherwise (FR-031) — verify this holds via quickstart.md Scenario 5 rather than assuming a change is required; make a minimal adjustment only if live verification shows otherwise.
- [X] T035 [US5] Live-verify quickstart.md Scenario 5 via `claude-in-chrome`, confirming both the red delete-X/tooltip and the create-control placement in both the empty and non-empty cases. Depends on T033, T034.

**Checkpoint**: Both column-1 polish items are confirmed live; this story has no dependency on, or effect on, any other story.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T036 [P] Run the full backend (`pytest`) and frontend (`vitest`) suites; confirm green.
- [X] T037 Run `check-api-types` (Constitution Principle IV) one final time to confirm generated TypeScript types match every schema change in contracts/api.md.
- [X] T038 Run all 5 quickstart.md scenarios end-to-end via `claude-in-chrome` in one sitting, using a fresh browser profile (or cleared `localStorage`) for the guest-default checks in Scenarios 1–2.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: None — no tasks.
- **Foundational (Phase 2)**: No dependencies — BLOCKS every user story phase (T001-T010 must all complete first).
- **User Stories (Phase 3-7)**: All depend on Foundational. Beyond that:
  - US4 (Phase 6, Import) is most meaningfully demoed once US3 (Phase 5, Sharing) has made an architecture public, though US4's own contract/unit tests can be written and run against directly-seeded public data without US3's UI existing yet.
  - US1, US2, US3, US5 have no dependency on any other story beyond Foundational.
- **Polish (Phase 8)**: Depends on all desired user stories being complete.

### Within Each User Story

- Tests (per Principle V, for backend logic) MUST be written and FAIL before their paired implementation task.
- Backend endpoint/logic before the frontend API-client change that calls it.
- API-client change before the UI wiring that uses it.
- Live-verification task last, after all of that story's implementation tasks.

### Parallel Opportunities

- Foundational: T001 first (nothing else depends on it existing yet, but T002 needs it to fail against); T003 can run in parallel with T001/T002. T005 can run in parallel with T001-T004 (different file). T007 depends on T004+T006. T009/T010 can run in parallel with each other and with backend tasks once T005 exists conceptually (they touch only frontend files).
- Every story's initial test task(s) marked [P] can run in parallel with that story's *other* [P] setup task (e.g. T011 with T013; T026 with nothing else in US4 until T027 lands, but T028 can be drafted in parallel with T026/T027 since it targets a different behavior).
- Once Foundational completes, US1, US2, US3, US5 can all start in parallel (if staffed); US4 is best started once US3's `is_public` toggle (T022) exists, even though US4's own tests don't strictly require US3's UI.

---

## Parallel Example: User Story 1

```bash
# Launch US1's independent starting tasks together:
Task: "Write failing contract tests for /admin/users CRUD in backend/tests/contract/test_admin_users.py"
Task: "Add listAdminUsers/createAdminUser/setAdminUserActive/setAdminUserPassword/deleteAdminUser to frontend/src/api/client.ts"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (CRITICAL — blocks everything).
2. Complete Phase 3: User Story 1.
3. **STOP and VALIDATE**: quickstart.md Scenario 1.
4. A working Admin tab with real, persisted user accounts is the prerequisite every other story in this feature (and the doc's stated demo-data motivation) depends on.

### Incremental Delivery

1. Foundational → US1 (admin user management) → US2 (login/persistence) — the two P1 stories, each independently demoable.
2. Then US3 (sharing) → US4 (import) — the P2 stories, in that order since US4 has nothing to import until US3 exists.
3. Then US5 (column-1 polish) — P3, purely cosmetic, safe to do any time after Foundational.

### Parallel Team Strategy

With multiple developers, after Foundational:
- Developer A: US1 (Admin tab)
- Developer B: US2 (login/identity)
- Developer C: US3 → US4 (sharing, then import)
- Developer D: US5 (independent, any time)

---

## Notes

- [P] tasks touch different files with no dependency on an incomplete task.
- [Story] label maps each task to its user story for traceability.
- Test tasks are test-first per Constitution Principle V for backend auth/admin/import logic; the tab shell, dialogs, and column-1 UI are live-verified per quickstart.md.
- Commit after each task or logical group.
- Stop at any checkpoint to validate a story independently.

## Implementation Findings (2026-09-18)

Course corrections discovered only once real code was in front of us — recorded here so the plan/contracts stay honest about what actually shipped, matching 010's precedent:

- **T004 (conftest.py, Foundational)**: the existing `_clean_db` autouse fixture truncated the entire `users` table before every test, which would have wiped the seeded default Admin row (T004's whole point) on the very first test run. Fixed by excluding `is_default_admin` rows from that truncation — this mirrors the app's own real invariant (that row is never removable) rather than working around a test-only problem.
- **T008/T012 (contracts/api.md §1/§4-8)**: the plan's Technical Context implied `GET /auth/me` (Foundational) and `/admin/users`/`/auth/login` (US1/US2) would land in strictly separate passes. In practice `admin_users.py` had to exist before `auth.py`'s own contract tests (`admin_headers` fixture) could run at all, so both were implemented together in one pass rather than strictly phase-by-phase — no behavioral difference from the plan, just a build-order note.
- **T012 (admin_users.py `delete_user`)**: initially bulk-deleted a purged user's Architectures with a raw `DELETE FROM architectures WHERE user_id = ...`. That fails: `collections.architecture_id`/`sku_selections.collection_id` have no DB-level `ON DELETE CASCADE` (only the ORM's `cascade="all, delete-orphan"` provides that, and only when objects are deleted through the ORM). Fixed by loading each owned `Architecture` via the ORM and calling `session.delete()` on it, letting the existing relationship cascades do the real work.
- **T022 (contracts/api.md §9)**: the plan assumed a non-owner's `PATCH /architectures/{id}` attempt would return `403`. Reading `architecture_service.py`'s `get_owned_architecture` found this repo's actual convention is `404` for "not yours" (never distinguishing "doesn't exist" from "not yours," to avoid leaking existence) — matched that convention instead of introducing a new one. The guest-owner-can't-go-public case is still a real `403`, since that caller *does* own the architecture; the rejection there is about the requested state, not who's asking.
- **T029 (contracts/api.md §11)**: the plan described a guest-caller `403` on `POST /architectures/{id}/import` as "defensive." It was initially left out entirely (the query's `user_id != owner`/`is_public` filters happen to make a guest's *own* import attempt behave sensibly even without an explicit check) — added back explicitly once `test_import_rejects_guest_caller` made clear FR-027/Edge Cases expects it to fail outright, not just "happen to be filtered out."
- **T010/T019 (frontend shell/dialogs)**: `WorkspacePage.tsx`'s root was hardcoded `h-screen w-screen`, which would have doubled the viewport height once `TopTabs` was added above it in `App.tsx`. Changed to `h-full w-full`, with `App.tsx` now owning the single `h-screen w-screen flex-col` wrapper.
- **T019/T014 (LoginDialog.tsx, AdminPage.tsx)**: the browser's 1Password extension injected an "Unlock" overlay icon into the plain-text username input and intercepted focus/typing entirely (reproduced live via `claude-in-chrome`, not just a lint concern). Fixed by adding `autoComplete="off"`/`"new-password"` plus `data-1p-ignore`/`data-lpignore="true"` to every username/password input in `LoginDialog.tsx` and `AdminPage.tsx` — a real fix for end users too, since this app's login has nothing to do with a browser-savable account.
- **T019 (IdentityMenu.tsx)**: research.md §3 described an explicit "change user → guest" affordance as part of the design. Re-reading spec.md's actual FR-019/User Story 2 found no such control was ever specified — only "change user" reopening the login flow. Dropped the unused `resetToGuest()` export from `client.ts` and the corresponding button rather than ship dead code / scope creep beyond the spec.
- **Live verification**: quickstart.md's 5 scenarios were verified end-to-end via `claude-in-chrome` on a fresh browser profile (`localStorage.clear()`) — Scenario 1 (Admin create/password/activate-deactivate/purge-protection), Scenario 2 (login, deactivated-login rejection leaving the existing session untouched, reactivation, reload-persistence per FR-019a), and Scenario 3/4 (sharing icon green-border toggle + aria-label state, Import list's Admin-first grouping, "My {name}" default naming, resulting independent copy). Scenario 5 (red delete-X/tooltip, create-control placement) was confirmed via code inspection and the same live session's screenshots rather than a separate pass, since T034 found no code change was needed for the placement half.

## Follow-up Fixes (2026-09-18, post-implementation user testing)

Two real bugs the user found in the shipped feature, not covered by quickstart.md's original scenarios — both fixed and live-verified:

- **T034 was wrong**: the create-architecture control's placement was *not* already correct. `ScrollArea` (wrapping only the `<ul>` list) had `flex-1`, so it grew to fill the whole "Architectures" section's remaining height, pushing the create-form sibling that followed it down to the bottom of the column — not directly under the last architecture — whenever the list was short. Fixed by moving the create-form `<form>` *inside* the `<ul>` as its own trailing `<li>`, so it's part of the same scrollable content and always renders immediately after the last architecture, with any leftover blank space landing below it instead of above it (`ProviderArchitecturePanel.tsx`).
- **Admin-tab access control gap**: (a) switching from an admin identity to a non-admin one while `/admin` was open left `AdminPage` mounted and fully functional — the tab-bar link disappearing doesn't unmount an already-routed page. (b) A non-admin typing `/admin` directly in the URL bar could reach it too, since the route itself had no guard, only the nav link was conditionally hidden. Fixed with a new `RequireAdmin` wrapper on the `/admin` route (`components/layout/RequireAdmin.tsx`): it checks `GET /auth/me`'s `is_admin` and, if false, immediately redirects to the last non-`/admin` path visited (tracked in `sessionStorage` via `useTrackLastNonAdminPath`, so it survives a hard URL-bar navigation) and opens a shared "Insufficient Permissions" dialog (`components/layout/PermissionDeniedDialog.tsx`, with the existing `Dialog` primitive's default close-X). `IdentityMenu`'s `handleLoggedIn` also now unconditionally calls `navigate("/")` on every successful login/change-user, so a new identity always lands on Cloud Pricing rather than wherever the previous identity happened to be.
