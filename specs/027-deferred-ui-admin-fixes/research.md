# Research: Deferred UI and Admin Fixes

Checked against the code on 2026-11-22 (branch `027-deferred-ui-admin-fixes`, on top of 026).

## R1: One menu behaviour for both header menus

- **Decision:** a new `HeaderMenu` component wraps Radix `Popover` with the header trigger
  styling (`HEADER_CONTROL`, `aria-expanded` fill), Escape-returns-focus-to-trigger (today's
  `closedByEscape` logic in `TopTabs.tsx`), ArrowDown on the trigger to open, and ArrowUp /
  ArrowDown between the menu's top-level items. The Cloud Pricing chevron and the person icon
  both use it. The architecture menu keeps its own ArrowRight / ArrowLeft into provider panels
  and its Escape-in-name-field rule, passed in as an `onEscapeKeyDown` hook.
- **Rationale:** FR-002 says the two menus must not drift apart; one wrapper is the only way to
  guarantee that. Today the chevron opens on Enter and Space only, and the provider list has no
  Up/Down, so the Cloud Pricing menu gains those two keys too: a small, documented improvement
  that US1-3 requires.
- **Alternatives:** copying the popover code into `IdentityMenu` (drifts, which is what FR-002
  forbids); Radix `DropdownMenu` for the user menu (different focus and typeahead behaviour from
  the Popover-based Cloud Pricing menu, so the two would not match).

## R2: Where the theme is stored, and the guest rule

- **Decision:** a new optional section `appearance: { theme: "light" | "dark" }` in the existing
  per-user preferences (019). The client never sends it for a guest; the server refuses a patch
  containing `appearance` from a guest with 403 `theme_not_saved_for_guests`. Absent means
  light. The client applies the theme from local state at once and saves through the existing
  queued, retried `patchSection` (FR-025 of 019), so a failed save never blocks.
- **Rationale:** reuses the account settings that already follow the user across devices
  (US2-2), with the guest exception enforced in one testable place (FR-005).
- **Alternatives:** a column on `users` (a migration for one value, and outside the typed
  preferences shape); browser storage only (doesn't follow the user, US2-2).

## R3: No light flash for a dark user on reload

- **Decision:** when a logged-in user's theme is applied, it is also written to
  `localStorage["cloud-pricing-theme"]` with the user ID. A short inline script in `index.html`
  adds `.dark` before first paint when the cached user ID equals the current identity. The
  account value, once loaded, wins and refreshes the cache. Log out and any guest identity
  remove the cache entry.
- **Rationale:** preferences load after the first render, so without a cache a dark user sees
  light for a moment on every reload. The cache is only a copy of the account's value and is
  never written for a guest, so the "guest theme isn't saved" rule (US2-3) still holds.
- **Alternatives:** waiting for preferences before rendering (slower first paint for everyone);
  accepting the flash (looks broken).

## R4: Proving contrast on every page in both themes

- **Decision:** keep `tests/unit/theme.contrast.test.ts` (token pairs from `index.css`) and add
  any new pairs it misses, including the agent UI's. Add an e2e scan with `@axe-core/playwright`
  (rule `color-contrast` only) over the workspace with an architecture open, the Agent tab with a
  Results pane, Trends, Admin, an open dialog and both open menus, in light and dark.
- **Rationale:** the token test proves the palette; only a rendered-page scan proves every
  element uses it (SC-002). Legibility of diagrams, icons and charts beyond contrast stays
  `[MANUAL]` (US2-6).
- **Alternatives:** manual checks only (Principle V: don't hand off what can be automated);
  Lighthouse (heavier, not page-state aware).

## R5: Log out

- **Decision:** `api.logOut()` sets the current identity (`cloud-pricing-current-identity-id`)
  back to the browser's guest ID (`cloud-pricing-guest-id`, kept since 001 and never
  overwritten). If the guest key is missing, `getGuestId()` creates a new one. The user menu
  first runs the 025 unsaved-work check (`UnsavedWorkDialog`: Save and continue / Discard and
  continue / Cancel; Cancel keeps the user logged in), then removes the theme cache, removes the
  `.dark` class, clears the TanStack Query cache (every query is identity-scoped) and the
  preferences store, and navigates to `/`. A guest row that no longer exists is recreated empty
  by `get_current_user`'s lazy creation, which is the spec's "new guest" (US3-4).
- **Rationale:** the guest ID is already kept for exactly this; no server change is needed, and
  logins stay as they are (Out of Scope).
- **Alternatives:** a server-side logout endpoint (there is no server session to end).

## R6: Trends history status on the Admin page

- **Decision:** frontend shows each provider's `history` in the existing provider rows:
  "Complete: N weeks, last built <date>"; "N weeks missing"; "Building (N of M weeks)"; "Failed: <error>";
  "No history yet" when `weeks_total` is 0 and `backfill` is `pending`. Backend: `_history_out`
  catches a read error and the field becomes `null`, shown as "Unavailable".
- **Rationale:** the data is already served (019, contracts §9); only the edge case of an
  unreadable state needs a server change (FR-013).
- **Alternatives:** a separate history endpoint (duplicates `system-info`, refreshes separately).

## R7: Icon issues for GCP and Azure, first-party only

- **Decision:**
  - `generate_provider_service_icon_map.py` also writes
    `backend/src/pricing_data/{gcp,azure}_service_icons.json` (`by_id`, `overrides`) from the
    same mapping as the TypeScript file. It is re-run on the current snapshots (2026-11-16), which
    also refreshes the TypeScript maps and the shipped SVGs from 020's 2026-11-02 run
    (clarification 2026-11-22); the changes are listed in tasks.md. A unit test checks each JSON
    equals its TypeScript map, so the canvas and the check can't disagree (FR-015).
  - `icon_coverage.py` becomes provider-aware: AWS unchanged; GCP reads services from `service`
    and `sku` (taxonomy) as the generator's `read_services` does, which moves into `src` so both
    share it; Azure from `price_item`. A service has an icon when its ID is in `by_id` (no
    service today has overrides without a `by_id` entry; the test keeps it that way).
  - First-party only (clarification 2026-11-22): GCP services whose taxonomy is only
    "Marketplace Services" or "Third Party Services" are counted into one
    `marketplace_without_icons` issue per provider instead of listed. Azure has no Marketplace
    services in its price list, so all its services are first-party.
  - The snapshot monitor runs the check for every provider after its active snapshot changes,
    not only AWS.
- **Rationale:** the same "new" rule and the same per-snapshot analysis as AWS (016), on each
  provider's own data (Principle II).
- **Alternatives:** reading the TypeScript files from the backend (fragile parsing, wrong
  direction of dependency); listing all 1,650 GCP services (rejected by the owner).

## R8: One Issues table for all providers

- **Decision:** `system-info` returns each provider's issues under `providers.<p>.issues` (it
  already does for the count) and the Issues table lists all providers' issues with a Provider
  column, AWS first, then GCP, then Azure; within each, new services first as today.
- **Rationale:** US5-1 says "with its provider"; one table keeps the Admin page as it is.
- **Alternatives:** one table per provider (more scrolling for a short list).
