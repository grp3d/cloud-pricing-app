# Feature Specification: Deferred UI and Admin Fixes

**Feature Branch**: `027-deferred-ui-admin-fixes`

**Created**: 2026-11-21

**Status**: Draft

**Input**: User description: "../speckit-inputs/cloud-pricing-app-deferred-ui-and-admin-fixes.md"
(written 2026-11-12, run after the agent features 023–026; follows constitution 1.3.0)

## Overview

The 2026-11-10 docs review found places where the app falls short of what its docs describe,
each marked "planned" or "not shown yet" on its `docs/features/` page. This feature closes them:

1. A **user menu** behind the person icon in the header, rebuilt to look and behave like the
   Cloud Pricing (architecture) menu. It holds the user's name, **Log in** or **Log out**, and a
   **Settings** section whose first item is the **colour theme**.
2. Each provider's **Trends history status** on the Admin page.
3. **Missing-icon issues for GCP and Azure** in the Admin Issues table, as AWS has today.

**Why:**
- **Theme:** the dark theme's colours exist and were checked for contrast, but nobody can turn
  it on.
- **Log out:** once logged in, a browser can't return to being a guest without clearing its site
  data. This matters on shared machines and when trying the app as a guest.
- **One home for user settings:** the person icon today only logs in or changes user. The theme
  now, and other user settings later, need one obvious place.
- **Trends history:** when Trends shows gaps or stale weeks, the Admin can't tell whether the
  history is still being built, has missing weeks, or has failed. The server knows; the page
  doesn't show it.
- **Icons:** the Admin learns about AWS services with no canvas icon from the Issues table. GCP
  and Azure services fall back to a generic icon and nobody is told.

## Clarifications

### Decisions made before specification (owner, 2026-11-12)

- The theme is saved only for logged-in users, not for guests.
- Log out returns to the earlier guest identity if it still exists, otherwise to a new guest.
- The theme switch lives in the user menu, not as a separate header control. The user menu is
  rebuilt to match the Cloud Pricing menu and holds: name or Guest; Log in / Log out; Settings.
- The Settings section is shown now, with Colour theme (Dark / Light) as its first item.
- There is no Change user: a logged-in user logs out, then logs in as someone else.

### Session 2026-11-22

- Q: GCP's latest snapshot has 1,750 services and 99 with icons; most of the rest are Marketplace
  or third-party software, which never get icons (020). Which GCP and Azure services does the
  Issues table report? → A: First-party services only. Marketplace and third-party services
  without an icon are counted in one summary line per provider, not listed.
- Q: The 020 icon maps came from the 2026-11-02 snapshots; regenerating them for the backend
  reads the 2026-11-16 ones. Keep the old maps or refresh? → A: Refresh. Icons aren't stored
  with architectures, so every canvas shows the refreshed icons with no approval step.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The user menu (Priority: P1)

Clicking the person icon in the header opens the user menu. It looks and behaves like the Cloud
Pricing menu: the same opening and closing, styling, hover and focus states, and keyboard use
(Enter, Space or ArrowDown on the icon opens it, the arrow keys move between items, Escape closes
it and returns focus to the icon). It contains, in order:

1. **The user's name**, or **Guest**: a label, not an action.
2. **Log in** for a guest; **Log out** for a logged-in user.
3. **Settings**: a section for the user's own settings. Its first and, for now, only item is
   **Colour theme**, which offers **Dark** in the light theme and **Light** in the dark theme.
   Later features add their settings here without redesigning the menu.

**Why this priority**: the menu is the home of both the theme switch and Log out; neither can be
reached without it.

**Independent Test**: as a guest, open the menu and see Guest, Log in, and Settings with Colour
theme; log in and see the username, Log out, and Settings with Colour theme; operate the whole
menu from the keyboard.

**Acceptance Scenarios**:

1. **Given** a guest, **When** they open the menu, **Then** it shows **Guest**, **Log in**, and
   Settings with Colour theme, and no Log out.
2. **Given** a logged-in user, **When** they open the menu, **Then** it shows their username,
   **Log out**, and Settings with Colour theme, and no Log in or Change user.
3. **Given** the user menu and the Cloud Pricing menu, **When** each is operated from the
   keyboard (open with Enter, Space or ArrowDown; move with the arrow keys; Escape), **Then**
   both respond the same way and Escape returns focus to the button that opened the menu.
4. **Given** the user menu and the Cloud Pricing menu, **When** they are compared side by side,
   **Then** they look the same (menu styling, hover and focus states). `[MANUAL: whether two
   menus look alike is a visual judgement]`
5. **Given** a guest, **When** they pick **Log in**, **Then** today's login flow starts
   (username, then password, or creating a password if the account has none).

---

### User Story 2 - Switch between the light and dark themes (Priority: P1)

**Why this priority**: the dark theme is built and checked but unreachable; this is the most
visible gap the review found.

**Independent Test**: pick Dark in the user menu and see the whole app switch at once; reload as
a logged-in user and see dark again; reload as a guest and see light.

**Acceptance Scenarios**:

1. **Given** the light theme, **When** the user picks **Dark** in the user menu, **Then** the
   whole app switches to the dark theme at once, with no reload, and the item now offers
   **Light**. Picking **Light** switches back the same way.
2. **Given** a logged-in user who chose dark, **When** they reload, or log in on another browser
   or device, **Then** the app opens in the dark theme: the choice is saved to their account
   like their other settings.
3. **Given** a guest who switches to dark, **When** the page is reloaded, **Then** the app opens
   in the light theme: a guest's theme is not saved.
4. **Given** a user who has never chosen a theme, **When** the app opens, **Then** it uses the
   light theme, as today.
5. **Given** either theme, **When** any page is shown (workspace, Trends, Admin, dialogs, menus,
   the Agent tab and its Results pane), **Then** its text and controls meet WCAG 2.1 AA contrast.
6. **Given** the dark theme, **When** the canvas, provider icons, Trends charts and Agent tab are
   shown on real data, **Then** they stay legible. `[MANUAL: legibility of diagrams, icons and
   charts beyond the measured contrast is a visual judgement]`

---

### User Story 3 - A logged-in user logs out (Priority: P2)

**Why this priority**: it fixes a real dead end (no way back to guest), but it affects fewer
people than the theme.

**Independent Test**: as a guest, create an architecture, log in, then log out: the menu shows
Guest and the guest's architecture is back.

**Acceptance Scenarios**:

1. **Given** a logged-in user who was a guest in this browser before logging in, **When** they
   pick **Log out**, **Then** the browser returns to that guest identity.
2. **Given** a user who has logged out, **Then** the menu shows **Guest** and **Log in**; the
   user's own architectures, saved settings (theme included) and agent conversation are no
   longer shown or applied; and the account itself is unchanged.
3. **Given** the earlier guest, **When** the user has logged out, **Then** that guest's
   architectures are listed again, and the workspace opens as it would for that guest.
4. **Given** the earlier guest no longer exists, or this browser has no earlier guest recorded,
   **When** the user logs out, **Then** a new guest is created and used.

---

### User Story 4 - The Admin sees each provider's Trends history status (Priority: P2)

The Admin page's System Information shows, for each provider, how far its Trends history has
been built.

**Why this priority**: it explains gaps and stale weeks on the Trends page; Admins only.

**Independent Test**: open System Information with one provider complete, one with missing weeks,
one building and one with no history, and see each state described.

**Acceptance Scenarios**:

1. **Given** a provider whose history is complete, **Then** the Admin sees how many weeks are
   built and when the history was last built.
2. **Given** a provider with missing weeks, **Then** the Admin sees how many weeks are missing.
3. **Given** a history build or backfill that is running, **Then** the Admin sees that it is
   running; **given** one that failed, the Admin sees its last error.
4. **Given** a provider with no history yet, **Then** the section says so, rather than showing
   zeros as if they were a result.
5. **Given** System Information is open, **When** it refreshes (every minute, and on Check now),
   **Then** the history status refreshes with it.

---

### User Story 5 - The Admin is told about GCP and Azure services with no icon (Priority: P3)

**Why this priority**: the canvas already falls back to a generic icon, so nothing breaks; this
only tells the Admin.

**Independent Test**: with a GCP or Azure snapshot holding a service that has no canvas icon,
open the Issues table and see it listed with its provider.

**Acceptance Scenarios**:

1. **Given** a first-party GCP or Azure service in the provider's active snapshot that has no
   canvas icon, **Then** it appears in the Admin Issues table with its provider, as AWS services
   do today.
2. **Given** such a service, **Then** it is marked "new" on the same rule as AWS: its service
   code isn't in that provider's previous snapshot.
3. **Given** any provider, **Then** the first-party services listed in the Issues table are
   exactly the first-party services the canvas shows with the generic icon.
4. **Given** Marketplace or third-party GCP services with no icon, **Then** they are not listed
   one by one; one summary line gives their count for that provider.

---

### Edge Cases

- **A logged-in user's theme choice fails to save:** it still applies for the session and is
  retried like other saved settings; it never blocks the user.
- **The system asks for reduced motion:** the theme switches with no transition, and the menu
  opens without animation, as the Cloud Pricing menu does.
- **Logging out with unsaved work:** the same confirmation the app gives today before leaving
  unsaved work; cancelling it keeps the user logged in.
- **Logging out with a pending agent proposal:** the proposal stays in the user's agent session
  (it's the user's, not the guest's) and nothing is saved by logging out.
- **The earlier guest has been removed, or the browser was only ever logged in:** logging out
  creates a new guest rather than failing.
- **A provider's history status can't be read:** that provider's history shows as unavailable,
  without breaking the rest of System Information.
- **A provider has no snapshot yet:** no icon issues are reported for it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The person icon in the header MUST open a user menu with, in order: the user's
  name or **Guest** (a label, not an action); **Log in** for a guest or **Log out** for a
  logged-in user; and a **Settings** section whose first item is **Colour theme**.
- **FR-002**: The user menu MUST share the Cloud Pricing menu's behaviour (opening and closing,
  keyboard use, focus return, reduced-motion handling) and styling, so the two can't drift
  apart.
- **FR-003**: **Change user** MUST be removed; switching accounts is Log out then Log in.
- **FR-004**: **Colour theme** MUST offer the theme the app is not in (Dark in light, Light in
  dark) and MUST switch the whole app at once, with no reload.
- **FR-005**: A logged-in user's theme MUST be saved to their account with their other settings
  and applied when the app opens; a guest's theme MUST NOT be saved, so a reload opens in light.
- **FR-006**: With no saved theme, the app MUST open in the light theme.
- **FR-007**: Both themes MUST meet WCAG 2.1 AA contrast for text and controls on every page,
  dialog and menu, including the Agent tab and its Results pane.
- **FR-008**: When a user logs in, the browser MUST remember the guest identity it had, so that
  **Log out** can return to it.
- **FR-009**: **Log out** MUST return the browser to that earlier guest if it still exists, and
  otherwise create and use a new guest. It MUST NOT change the account.
- **FR-010**: After Log out, nothing of the logged-in user's MUST remain shown or applied: their
  architectures, saved settings (theme included) and agent conversation.
- **FR-011**: Log out MUST ask the same confirmation the app asks today before leaving unsaved
  work.
- **FR-012**: System Information MUST show, for each provider, its Trends history: weeks built
  and when it was last built; how many weeks are missing; whether a build or backfill is
  running; the last error if one failed; and "no history yet" where there is none.
- **FR-013**: The history status MUST refresh with the rest of System Information, and a
  provider whose status can't be read MUST show as unavailable without hiding the rest.
- **FR-014**: The Admin Issues table MUST report first-party GCP and Azure services that have no
  canvas icon, with their provider, as it does for AWS, using the same "new" rule (the service
  code isn't in that provider's previous snapshot). Marketplace and third-party services with no
  icon MUST NOT be listed one by one; one summary line per provider gives their count.
- **FR-015**: The icon check MUST use the same icon data the canvas uses, so the Issues table
  and the canvas always agree on which services get the generic icon.
- **FR-016**: A provider with no snapshot MUST report no icon issues.

### Key Entities *(include if feature involves data)*

- **Theme preference**: light or dark; part of a logged-in user's saved settings; absent means
  light. Never stored for a guest.
- **Earlier guest identity**: the guest a browser had before logging in, remembered in that
  browser so Log out can return to it.
- **Trends history status**: per provider, the weeks built out of the total, the missing weeks,
  whether a build or backfill is running, the last error and when it was last built (already
  known to the server).
- **Icon issue**: a first-party service in a provider's active snapshot with no canvas icon,
  with its provider, name and whether it is new since the previous snapshot; plus, per provider,
  the count of Marketplace and third-party services with no icon.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can switch the theme in at most two clicks (open the menu, pick the theme),
  and the whole app changes within one second, with no reload.
- **SC-002**: 100% of text and controls checked on every page, dialog and menu meet WCAG 2.1 AA
  contrast in both themes.
- **SC-003**: A logged-in user's theme is applied on 100% of later app opens, in any browser; a
  guest's never is.
- **SC-004**: In 100% of tests, Log out returns to the earlier guest when it exists, and to a new
  guest otherwise, with none of the logged-in user's architectures or settings left showing.
- **SC-005**: An Admin can tell, for each provider and without leaving the Admin page, whether
  its Trends history is complete, missing weeks, building, failed, or not started.
- **SC-006**: For every provider, the first-party services in the Issues table match the
  first-party services the canvas shows with the generic icon, with no omissions and no extras.

## Assumptions

- Logins are not a security boundary (owner's decision); Log out only returns the browser to a
  guest. It doesn't end a server session or revoke anything.
- Account-saved settings, with save-and-retry, already exist and today are saved for guests too;
  the theme is the one setting that isn't saved for guests.
- The dark theme's colours already exist and were checked for contrast; this feature turns them
  on and fixes any element that falls short, including the agent UI added since (023–026).
- The server already reports each provider's Trends history status; only the Admin page shows
  it.
- The canvas already has icon data for GCP and Azure (020); the icon check reads that same data.
- A guest still can't use the Agent tab (023); after logging out the Agent tab shows as it does
  for any guest.

## Out of Scope

- Following the operating system's light or dark setting automatically.
- Saving a guest's theme choice (decided: not saved).
- Any user settings beyond the theme; the Settings section only makes room for them.
- Changing how logins work.
- Adding icons by hand or new icon overrides for the GCP and Azure services found. Re-running the
  020 icon generator on the current snapshots, which refreshes the maps the canvas uses, is in
  scope (clarification 2026-11-22).
- Other open follow-ups: a cleanup job for guest IDs no longer used; readable GCP and Azure
  names on the canvas boxes (021); branching connectors (019).
