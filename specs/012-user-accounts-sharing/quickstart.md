# Quickstart: User Accounts, Administration, and Architecture Sharing

Manual/live-verification guide for this feature's user stories (spec.md). Run against a local dev stack with this feature's migration applied (data-model.md's seeded default Admin row, `username='Admin'`, password `admin123`).

## Prerequisites

- Backend running with Alembic migrations applied, including this feature's `0004_user_accounts_sharing` migration (research.md §6).
- Frontend dev server running (`frontend/`), pointed at that backend.
- A fresh browser profile (or cleared `localStorage`) so the "new browser defaults to guest" behavior (FR-015) is genuinely observed, not masked by a prior session.

## Scenario 1 — Admin manages users (User Story 1)

1. Open the person icon (top-left), choose "login", enter username `Admin`, password `admin123`. **Expect**: logged in; icon now shows "Admin".
2. **Expect**: the tab bar shows "Cloud Pricing" (active), "Trends" (visible, disabled), and "Admin" (visible).
3. Open the Admin tab. Click "Create New User", enter username `demo1`. **Expect**: a new row appears, Active checked, password action reads "Create".
4. Click "Create" on `demo1`'s row, submit a password (e.g. `hello123`) in the popup. **Expect**: the row now shows a 4-character hash suffix and the action reads "Update".
5. Submit a different password via "Update". **Expect**: the displayed hash suffix changes.
6. Uncheck `demo1`'s Active checkbox. **Expect**: unchecked, persists on refresh; `demo1` can no longer log in (Scenario 2, step 6).
7. Create a second user `demo2`, then click "remove user" on it and confirm. **Expect**: `demo2` disappears from the table; `demo1` and `Admin` are unaffected.
8. View the `Admin` row itself. **Expect**: its Active checkbox and "remove user" control are both disabled.

## Scenario 2 — Login, change user, guest fallback, persistence (User Story 2)

1. In guest mode (default on a fresh browser), open the person icon. **Expect**: shows "Guest" and a "login" action.
2. Re-activate `demo1` from the Admin tab (undo Scenario 1 step 6) and set its password to `pw1` if not already set.
3. Log in as `demo1` / `pw1`. **Expect**: icon shows "demo1" and a "change user" action.
4. Reload the page (and, if convenient, fully restart the browser). **Expect**: still logged in as "demo1" with no login prompt (FR-019a).
5. Use "change user", enter a nonexistent username `nope`. **Expect**: popup closes silently, still logged in as "demo1" (not reset to guest — only a *fresh* browser defaults to guest; an existing login persists through a failed change-user attempt).
6. Use "change user" again, enter `demo1` with the wrong password. **Expect**: same silent-close behavior.
7. Deactivate `demo1` from the Admin tab (as `Admin`, in a second browser/profile), then in `demo1`'s browser use "change user" → attempt to log back in as `demo1`. **Expect**: fails the same way as a wrong password (FR-008).
8. Use "change user" → enter a brand-new username `demo3` (no account exists yet). **Expect**: prompted to create a password; submitting one creates the account and logs in as `demo3`.

## Scenario 3 — Owner marks an architecture public/private (User Story 3)

1. Logged in as `demo3` (or any named user), create an architecture "Web App".
2. In column 1, view its row. **Expect**: a sharing icon with no border; hover shows "Click to make public".
3. Click it. **Expect**: green border; hover now shows "Click to make private".
4. Click again. **Expect**: back to no border, "Click to make public".
5. Log out to guest, create a guest-mode architecture. **Expect**: no sharing icon appears on it at all (FR-022).

## Scenario 4 — Import another user's public architecture (User Story 4)

1. As `demo3`, make "Web App" (Scenario 3) public.
2. As `Admin`, also create and publish an architecture, e.g. "Reference Setup".
3. Log in as `demo1`. Open column 1's "Import" action. **Expect**: two groups — "Admin" first (regardless of alphabetical order), then "demo3" — each listing its public architecture(s) sorted by name; `demo1`'s own architectures never appear here even if public.
4. Select "Web App". **Expect**: prompted to name the copy, pre-filled "My Web App".
5. Confirm without editing. **Expect**: a new architecture "My Web App" appears in `demo1`'s own column-1 list, independent of the original.
6. As `demo3`, delete or edit the original "Web App". **Expect**: `demo1`'s "My Web App" copy is unaffected.
7. Log out to guest. **Expect**: no "Import" action is shown at all (FR-027).

## Scenario 5 — Column-1 delete affordance and create-control placement (User Story 5)

1. As a fresh named user with zero architectures, view column 1. **Expect**: the create-architecture control (name field + button) sits directly under the "AWS Architectures" heading.
2. Create one architecture. **Expect**: the create control now sits below that architecture in the list.
3. Hover the delete "✕" for any architecture. **Expect**: rendered in red, tooltip reads "Click to remove".
