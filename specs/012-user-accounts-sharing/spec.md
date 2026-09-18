# Feature Specification: User Accounts, Administration, and Architecture Sharing

**Feature Branch**: `012-user-accounts-sharing`

**Created**: 2026-09-18

**Status**: Draft

**Input**: User description: "see docs/functionality_2026-09-18.md for the next round of functional updates". The source document covers, in one bundled round: (1) introducing real backend-persisted user accounts so the app can be pre-loaded with demo architectures — three top-level tabs (Cloud Pricing, a disabled Trends placeholder, and an Admin tab visible only to administrators), an Admin-tab table for creating/deactivating/password-managing/purging users, a top-left account icon driving login/guest-mode/change-user, and a seeded default Admin account; (2) letting an architecture's owner mark it public/private via an icon in column 1; (3) letting any logged-in user import another user's public architecture via a grouped, sorted "Import" list, prompting for a copy name defaulting to "My {original name}"; and (4) two small column-1 polish items (a red delete "X" with a "Click to remove" hover, and relocating the create-architecture control to sit under the heading or below the last architecture).

## Clarifications

### Session 2026-09-18

- Q: Does a logged-in identity stay logged in across a page reload or browser restart in that same browser, or does every fresh page load reset back to guest even if the user logged in moments earlier? → A: Persisted — once logged in, that browser stays logged in as that user across reloads/restarts until "change user" is used or the admin deactivates them.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Administrator manages user accounts via a role-gated Admin tab (Priority: P1)

The application now presents three tabs: "Cloud Pricing" (today's existing experience, active by default), "Trends" (visibly present but disabled — a placeholder for later), and "Admin" (shown only when the current identity is an administrator). In the Admin tab, the administrator sees a table of every user account and can create a new user (username only), toggle each user's Active status, set or update each user's password via a popup, and permanently purge a single user (after confirmation), removing that user and everything they own. A default Admin account is seeded automatically the first time the system starts, with a working default password, and cannot be deactivated or purged.

**Why this priority**: Every other capability in this feature — logging in as someone other than a guest, marking an architecture public, importing a shared architecture — requires real, distinct user accounts to exist first, and the Admin tab is the only way accounts get created.

**Independent Test**: Log in as the seeded default Admin account, confirm the Admin tab is visible and the Trends tab is visibly present but inert, create a new user by username alone, set a password for it via the popup, deactivate and reactivate it via the checkbox, and purge a different (non-default) user with confirmation — verifying only that one user disappears from the table.

**Acceptance Scenarios**:

1. **Given** the app has just loaded and no one has logged in, **When** the user views the tab bar, **Then** "Cloud Pricing" is the active tab, "Trends" is visible but disabled/non-interactive, and "Admin" is not shown.
2. **Given** the current identity is the administrator, **When** they view the tab bar, **Then** the "Admin" tab is visible alongside "Cloud Pricing" and "Trends."
3. **Given** the Admin tab is open, **When** the administrator clicks "Create New User" and enters only a username, **Then** a new row appears with Active checked by default and a "Create" (not "Update") password action.
4. **Given** a user with no password, **When** the administrator uses that user's password "Create" action and submits a password in the popup, **Then** the row shows the last 4 characters of the stored password's hash and the action becomes "Update."
5. **Given** a user whose password action is "Update", **When** the administrator submits a new password via the popup, **Then** the displayed hash suffix changes to reflect the new password.
6. **Given** a non-default user's checked Active checkbox, **When** the administrator unchecks it, **Then** that user can no longer log in, while their existing architectures and data remain unchanged.
7. **Given** a non-default user, **When** the administrator clicks "remove user" and confirms, **Then** that single user and only that user's data/architectures are permanently removed from the system.
8. **Given** the default Admin account's row, **When** the administrator views it, **Then** its Active checkbox is disabled and its "remove user" action is disabled.
9. **Given** the system has just been initialized, **When** it starts for the first time, **Then** a default Admin account already exists with a working password, with no manual setup step required.

---

### User Story 2 - Any user logs in, switches identity, or returns to guest (Priority: P1)

A small person icon in the top-left corner reflects and controls the current identity. In guest mode (the default, unchanged from today), opening it shows "Guest" and a "login" action. Choosing "login" opens a popup asking for a username; if that account has no password yet, the person is prompted to set one there and is then logged in; if it has one, they must enter it correctly to be logged in. Entering a username that doesn't exist, or the wrong password for one that does, simply closes the popup and leaves the person in guest mode — no error message. Once logged in, opening the icon shows the current username and a "change user" action, which reopens the same login flow to switch to a different account. Guest mode itself is unchanged: architectures created as a guest still live only in that browser.

**Why this priority**: This is the only way anyone becomes a named, backend-identified user — the prerequisite for every sharing/import capability in this feature — and it is a distinct end-user journey from the administrator's own management tasks in User Story 1.

**Independent Test**: With a non-default user account already created and given a password (via User Story 1), open the person icon while in guest mode, log in as that user, confirm the icon now shows their username, use "change user" to switch to a different valid account, and confirm an invalid attempt safely falls back to guest instead of erroring.

**Acceptance Scenarios**:

1. **Given** no one is logged in, **When** the user opens the top-left icon, **Then** it shows "Guest" and a "login" action.
2. **Given** the login popup, **When** the user enters a username that has no password set, **Then** they are prompted to create one, and doing so logs them in as that user.
3. **Given** the login popup, **When** the user enters a username with a password set and enters the correct password, **Then** they are logged in as that user.
4. **Given** the login popup, **When** the user enters a username that doesn't exist, or the wrong password for one that does, **Then** the popup closes and the user remains in guest mode, with no error shown.
5. **Given** a user logged in as "Username", **When** they open the top-left icon, **Then** it shows "Username" and a "change user" action.
6. **Given** a logged-in user, **When** they use "change user" and successfully log in as a different account, **Then** the icon updates to reflect the new username.
7. **Given** a user in guest mode, **When** they create or edit an architecture, **Then** it is stored only in that browser, exactly as it behaves today.
8. **Given** an administrator has deactivated a user's account, **When** that user next attempts to log in, **Then** the attempt fails the same way an incorrect password would (popup closes, remains guest).
9. **Given** a user logged in as "Username", **When** they reload the page or reopen the browser, **Then** they remain logged in as "Username" without needing to log in again.

---

### User Story 3 - Owner marks an architecture public or private (Priority: P2)

Next to each architecture's existing delete ("X") control in column 1, a new icon lets its owner mark the architecture public (shareable, importable by any other user) or private (the default for every architecture). No border on the icon means private; a green border means public. Hovering shows "Click to make public" or "Click to make private," depending on the current state.

**Why this priority**: Nothing can be imported until something has been made available to import — this is the enabling half of sharing, and it is valuable and demonstrable on its own even before another user actually imports anything.

**Independent Test**: While logged in as a non-guest user with at least one architecture, click its sharing icon, confirm it gains a green border and the hover text flips to "Click to make private," click it again, and confirm it returns to no border with hover text "Click to make public."

**Acceptance Scenarios**:

1. **Given** a logged-in user's architecture that has never been shared, **When** they view its row, **Then** the sharing icon has no border and hovering shows "Click to make public."
2. **Given** that icon, **When** the owner clicks it, **Then** the architecture becomes public, the icon gains a green border, and hovering now shows "Click to make private."
3. **Given** a public architecture's icon, **When** the owner clicks it again, **Then** the architecture becomes private again and the icon returns to no border.
4. **Given** a guest (not logged in), **When** they view their own column-1 architecture list, **Then** no sharing icon is shown, consistent with guest architectures never being shareable.

---

### User Story 4 - A user imports another user's public architecture (Priority: P2)

An "Import" action next to the "AWS Architectures" heading in column 1 lists every other user's public architectures, grouped by owning username. Username groups are sorted alphabetically, except the administrator's group (if present) always appears first. Within a group, architecture names are sorted alphabetically. A user with no public architectures doesn't appear at all. Picking one prompts the importer to name their copy, defaulting to "My {original name}."

**Why this priority**: This is the payoff half of sharing — it's what actually lets someone stand up a ready-made demo architecture — but it has nothing to show until User Story 3 has made at least one architecture public.

**Independent Test**: With a second logged-in user and at least one public architecture owned by someone else, open the Import list, confirm the grouping/sorting rules, pick an architecture, accept or edit the default "My {name}" suggestion, and confirm a new, independently-owned architecture appears in the importer's own list.

**Acceptance Scenarios**:

1. **Given** at least two users each own one or more public architectures, **When** a user opens the Import list, **Then** entries are grouped by owning username, groups are sorted alphabetically except the administrator's group is always first, and architecture names within each group are sorted alphabetically.
2. **Given** a user who owns no public architectures, **When** the Import list is opened, **Then** that user's group does not appear at all.
3. **Given** the Import list, **When** the importer selects an architecture named "Web App", **Then** they are prompted to name their copy, pre-filled with "My Web App."
4. **Given** the naming prompt, **When** the importer confirms (with or without editing the suggested name), **Then** a new architecture with that name appears in their own list, fully independent of the original.
5. **Given** an imported copy now exists, **When** the original owner later edits or deletes the source architecture, **Then** the imported copy is unaffected.
6. **Given** a guest (not logged in), **When** they view column 1, **Then** no Import action is shown, consistent with sharing/importing being unavailable to guests.

---

### User Story 5 - Column 1 polish: delete affordance and create-architecture placement (Priority: P3)

The existing delete ("X") control for each architecture in column 1 is shown in red, with hover text "Click to remove." The create-architecture control (button and name field) moves to sit directly under the "AWS Architectures" heading when the list is empty, or below the last architecture when it is not.

**Why this priority**: Pure visual/layout polish with no dependency on, or blocking of, any other story in this feature — safe to land last.

**Independent Test**: Open column 1 with zero architectures and confirm the create control sits directly under the heading; add one architecture and confirm the create control has moved below it and the delete "X" is red with "Click to remove" on hover.

**Acceptance Scenarios**:

1. **Given** column 1's architecture list, **When** the user hovers the delete "X" for any architecture, **Then** it is rendered in red and shows "Click to remove."
2. **Given** no architectures exist yet, **When** the user views column 1, **Then** the create-architecture control appears directly under the "AWS Architectures" heading.
3. **Given** one or more architectures exist, **When** the user views column 1, **Then** the create-architecture control appears below the last architecture, not above the list.

---

### Edge Cases

- What happens when the administrator attempts to deactivate or purge the default Admin account? Both controls are disabled for that one account specifically (User Story 1).
- What happens when the administrator tries to create a user with a username that already exists? The attempt is rejected — usernames are unique.
- What happens to a user's already-imported (copied) architectures when the original source user is later purged? They are unaffected — each import is an independent copy from the moment it is created, owned entirely by the importer.
- What happens if a guest attempts to reach the Admin tab, the sharing icon, or the Import action directly? None of them are shown or reachable for a guest identity.
- What happens when a currently-active browser session belongs to a user the administrator just deactivated or purged? The change takes effect the next time that identity is authenticated (e.g., their next login attempt); this feature does not require instantly invalidating a session that was already open when the change was made.
- What happens when an architecture is imported and the copy's default suggested name collides with a name the importer already uses? The importer can edit the suggested name before confirming; the system does not need to auto-disambiguate on their behalf.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST present three top-level tabs — "Cloud Pricing", "Trends", and "Admin" — with "Cloud Pricing" active by default on page load.
- **FR-002**: System MUST render the "Trends" tab as visibly present but disabled/non-functional for every identity, including guests.
- **FR-003**: System MUST show the "Admin" tab only when the current identity is an administrator, and MUST hide it entirely for every other identity, including guests and non-admin logged-in users.
- **FR-004**: System MUST provide an Admin-tab table listing every user account, showing username, Active status, password state, and a purge control for each.
- **FR-005**: System MUST let the administrator create a new user by supplying only a username; every other field starts at its default (Active, no password set).
- **FR-006**: System MUST reject creating a new user whose username already exists in the system.
- **FR-007**: System MUST let the administrator toggle a user's Active status via a checkbox, defaulting to Active at creation.
- **FR-008**: System MUST prevent a deactivated user from logging in, while preserving all of that user's existing data and architectures unchanged.
- **FR-009**: System MUST show the last 4 characters of a user's stored password hash, alongside an "Update" action, when that user has a password; System MUST show a "Create" action instead when the user has no password.
- **FR-010**: System MUST let the administrator set or change a user's password via a popup, store only a hash of it (never the plain-text password), and MUST NOT display the entered password back to the administrator afterward.
- **FR-011**: System MUST let the administrator permanently purge exactly one selected user, after an explicit confirmation step, removing that user and every architecture and related record they own, without affecting any other user's data.
- **FR-012**: System MUST seed a default administrator account automatically the first time the system initializes, with a working default password, requiring no manual setup.
- **FR-013**: System MUST prevent the default administrator account from being deactivated or purged, disabling those specific controls for that account only.
- **FR-014**: System MUST show a person icon in the top-left of the screen at all times, reflecting the current identity.
- **FR-015**: System MUST default every new browser session to guest mode, behaving exactly as the application does today (architecture data persisted only in that browser).
- **FR-016**: System MUST, while in guest mode, show "Guest" and a "login" action when the person icon is opened.
- **FR-017**: System MUST, when "login" is chosen, prompt for a username, then: if that user has no password, prompt to create one and log the user in on success; if that user has a password, prompt for it and log the user in only when it matches.
- **FR-018**: System MUST close the login prompt and leave the user in guest mode, with no error message, when the entered username does not exist or the entered password is incorrect.
- **FR-019**: System MUST, once logged in, show the current username and a "change user" action when the person icon is opened, and MUST let "change user" reopen the same login flow to switch identities.
- **FR-019a**: System MUST persist a logged-in identity across page reloads and browser restarts in that same browser, keeping the user logged in as that account until they use "change user" or an administrator deactivates the account — mirroring how the guest-mode identity is already persisted in that browser today.
- **FR-020**: System MUST let an owner mark their own architecture as public or private via a dedicated icon in column 1, defaulting every architecture to private.
- **FR-021**: System MUST render that icon with no border while private and with a green border while public, and MUST show "Click to make public" or "Click to make private" on hover according to its current state.
- **FR-022**: System MUST NOT show the public/private icon, or any other sharing affordance, for architectures owned by a guest.
- **FR-023**: System MUST provide an "Import" action in column 1 that lists every public architecture not owned by the current user, grouped by owning username.
- **FR-024**: System MUST sort those username groups alphabetically, except MUST always place the administrator's group first regardless of alphabetical order.
- **FR-025**: System MUST sort architecture names alphabetically within each username group.
- **FR-026**: System MUST omit a user's group entirely from the Import list when that user currently owns no public architectures.
- **FR-027**: System MUST NOT show the Import action to a guest.
- **FR-028**: System MUST, when an architecture is selected from the Import list, prompt the importer for a name, pre-filled with "My {original architecture name}."
- **FR-029**: System MUST create a full, independent copy of the selected architecture — including its collections, connectors, and service selections — owned by the importing user under the confirmed name, and MUST leave the original architecture and its owner unaffected by later changes to either copy.
- **FR-030**: System MUST render each architecture's existing delete ("X") control in column 1 in red and show "Click to remove" on hover.
- **FR-031**: System MUST position the create-architecture control (button and name field) directly under the "AWS Architectures" heading when no architectures exist, and below the last architecture otherwise.

### Key Entities

- **User**: A named account in the system. Key attributes: unique username, active/inactive status, password (stored as a hash, optionally unset), administrator flag. Relationships: owns zero or more Architectures.
- **Architecture** *(existing entity, extended)*: Gains an owner (a User) and a public/private visibility flag. Importing one produces a new, fully independent Architecture — with its own copies of every nested Collection, Connector, and Service Selection — owned by the importer.
- **Current Identity** *(session concept, not necessarily a stored record)*: Tracks which User — or "Guest" — is active in a given browser at a given time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An administrator can create a new user and give them a working password in under 1 minute, without leaving the Admin tab.
- **SC-002**: 100% of purge actions remove exactly one user's data and leave every other user's architectures and accounts completely intact.
- **SC-003**: A user can switch from guest to a named identity, or between two named identities, in 3 clicks or fewer.
- **SC-004**: An owner can change an architecture's public/private state in a single click, with the new state visible immediately.
- **SC-005**: A user can locate and import any architecture another user has shared using only the grouped, sorted Import list, without needing to ask that user directly which architectures exist.
- **SC-006**: Zero non-administrator identities, including guests, can view or reach the Admin tab's user-management content.
- **SC-007**: Guest-mode behavior (browser-only persistence) is unchanged for every user who never logs in.

## Assumptions

- Only the single seeded default Admin account has administrator privileges in this version; no interface is described for granting admin rights to another user.
- "Purge" means permanent, irreversible removal from the system — distinct from the existing soft-delete "remove" pattern already used for architectures — consistent with the word choice and its explicit removal of "all associated data."
- Importing an architecture creates a one-time, fully independent copy at the moment of import, not a live link back to the original — consistent with the described "prompt to name it" step, which implies cloning rather than referencing.
- Self-service password changes by a regular user (outside the Admin tab) are out of scope for this version; only the Admin tab's Update action and the first-time "create a password" step during login can set a password.
- Password storage uses a standard one-way hash, not reversible encryption; the UI only ever shows the last 4 characters of that hash, never the password itself.
- No password complexity rules are enforced beyond the account needing some non-empty password.
- Deactivating or purging a user takes effect on that user's next authentication check (e.g., their next login attempt); this version does not need to immediately invalidate a session that was already active when the change was made.
- The Trends tab's actual functionality is out of scope for this feature; it exists only as a visible, disabled placeholder.
- Guest-mode architectures remain entirely client-browser-persisted, exactly as today, and are never eligible for sharing or import.
