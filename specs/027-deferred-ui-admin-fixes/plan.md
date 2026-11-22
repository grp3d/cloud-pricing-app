# Implementation Plan: Deferred UI and Admin Fixes

**Branch**: `027-deferred-ui-admin-fixes` | **Date**: 2026-11-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/027-deferred-ui-admin-fixes/spec.md`

## Summary

Four small, independent changes, mostly in the frontend:

- **User menu (US1):** the person icon opens a popover built on a new shared `HeaderMenu`, which
  the Cloud Pricing menu also moves onto, so the two share opening, keyboard use, focus return
  and styling (R1). It holds the name or Guest, Log in / Log out and a Settings section with
  Colour theme. Change user goes.
- **Theme (US2):** a new optional `appearance.theme` section in the account preferences
  (`light` | `dark`, absent = light), refused for guests by the server and never sent by the
  client for them (R2). The app toggles the existing `.dark` class on `<html>` at once; a
  logged-in user's last theme is cached in the browser only to avoid a light flash on reload
  (R3). An axe colour-contrast scan of every page in both themes is added to the e2e suite, next
  to the existing token-pair contrast test (R4).
- **Log out (US3):** the browser already keeps its guest ID (`cloud-pricing-guest-id`); Log out
  points the current identity back at it after the unsaved-work check, and clears every
  identity-scoped query and the theme cache (R5). A removed guest is recreated empty by the
  existing lazy user creation, which is the spec's "new guest".
- **Admin (US4, US5):** System Information shows each provider's history from the existing
  `providers.<p>.history`, which becomes nullable when its state can't be read (R6). The icon
  check runs for GCP and Azure from JSON maps the 020 generator now writes beside its TypeScript
  maps (re-run on the current snapshots, which also refreshes the canvas's GCP and Azure icons), lists first-party services only and adds one Marketplace count line per provider (R7);
  the Issues table gains a Provider column (R8).

## Technical Context

**Language/Version**: Python 3.12 (backend); TypeScript 5.6 with React 18.3 (frontend).

**Primary Dependencies**: FastAPI, Pydantic 2, DuckDB (icon check). Frontend: TanStack Query,
Radix UI (Popover), Tailwind. One new dev dependency: `@axe-core/playwright` for the contrast
scan (R4).

**Storage**:
- PostgreSQL: the existing per-user preferences JSON gains an optional `appearance` section. No
  migration: the section is optional and additive, so `schema_version` is unchanged.
- Browser `localStorage`: the existing guest and current-identity keys; a new theme cache for
  logged-in users only (R3).
- Pricing data: read-only, unchanged.

**Testing**:
- pytest unit (`test_icon_coverage.py`, `test_icon_map_consistency.py`): icon coverage for GCP
  and Azure (first-party filter, Marketplace count, "new" rule, no snapshot → no issues), the
  JSON maps match the TypeScript maps;
- pytest contract (`test_preferences.py`, `test_admin_system_info.py`): `appearance` saved for a
  logged-in user and refused for a guest; `system-info` with a history state that can't be read
  and with per-provider issues;
- Vitest: `HeaderMenu` keyboard and focus, the user menu's items for guest and user, the theme
  store (apply, save only when logged in, cache), Log out (back to the guest ID, queries cleared,
  unsaved-work prompt), the history status cell for each state, the Issues table's Provider
  column and summary line;
- Playwright e2e: theme switch and persistence across reload (user) and reset (guest), Log in →
  Log out returns the guest's architectures, both menus from the keyboard, and the axe contrast
  scan in both themes.

**Target Platform**: the existing Docker Compose stack and local dev on macOS. No deploy until
the owner says so.

**Project Type**: web application (`backend/` + `frontend/`).

**Performance Goals**: the theme switches within one frame of the click (SC-001: under one
second); the icon check for GCP's ~1,750 services adds under 1 s to a snapshot switch.

**Constraints**: no change to how logins work (Assumptions); no hand-edited generated files
(020); reduced motion respected (existing `prefers-reduced-motion` rules).

**Scale/Scope**: 3 header/menu components, 1 preferences section, 2 Admin components, 1
backend check extended to two providers, 1 generator script.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Pricing Data Integrity | No price, total or pricing query changes. | Pass |
| II. Provider-Neutral Data Model | The icon check takes the provider as a parameter and reads each provider's own map and service table; no AWS shape is imposed on GCP or Azure. | Pass |
| III. Cost Transparency | Unaffected. | Pass |
| IV. Typed Contracts | `appearance` is a typed, strict section of the preferences schema; `history` becomes `HistoryOut \| None`; `IssueOut` gains `provider` and a `marketplace_without_icons` kind with `count`. Frontend types regenerated from OpenAPI. | Pass |
| V. Test-First | The icon check and the preferences rule (user-defined data) are test-first. Presentational menu and Admin cells may be tests-after. Every acceptance scenario and SC maps to a test or is `[MANUAL]` (spec US1-4, US2-6); tasks.md gets the coverage table. | Pass |
| VI. Simplicity & YAGNI | One shared menu wrapper, not a menu framework; Settings holds one item; no OS-theme following; no new tables. | Pass |
| VII. Agent acts as the user | The agent is untouched; after Log out the Agent tab shows as for a guest (023's rule). | Pass |
| VIII. Replaceable models, bounded cost | Unaffected; no paid calls. | Pass |

No violations. Re-checked after Phase 1: still passes; the one new dev dependency is a test tool
only.

## Project Structure

### Documentation (this feature)

```text
specs/027-deferred-ui-admin-fixes/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── preferences-api.md
│   ├── admin-system-info.md
│   └── user-menu-ui.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── scripts/generate_provider_service_icon_map.py   # also writes the JSON maps (R7)
├── src/
│   ├── api/admin_system.py                         # history may be null; per-provider icon issues
│   ├── api/preferences.py                          # appearance refused for guests (R2)
│   ├── models/schemas.py                           # Appearance, HistoryOut | None, IssueOut
│   └── pricing_data/
│       ├── icon_coverage.py                        # provider-aware, first-party filter
│       ├── gcp_service_icons.json                  # generated (new)
│       ├── azure_service_icons.json                # generated (new)
│       └── active_snapshot.py                      # run the icon check for every provider
└── tests/{unit,contract}/

frontend/
├── e2e/{user-menu,theme}.spec.ts                   # new
├── src/
│   ├── api/client.ts                               # logOut(): back to the guest ID
│   ├── components/layout/
│   │   ├── HeaderMenu.tsx                          # new shared popover menu (R1)
│   │   ├── UserMenu.tsx                            # replaces IdentityMenu.tsx
│   │   └── TopTabs.tsx                             # both menus on HeaderMenu
│   ├── components/admin/SystemInformationSection.tsx  # history status, Provider column
│   ├── lib/theme.ts                                # new: apply, save, cache (R2, R3)
│   └── lib/preferences.ts                          # the appearance section
└── index.html                                      # pre-paint theme from the cache (R3)
```

**Structure Decision**: the existing web application layout; no new packages or folders beyond
the files above.

## Complexity Tracking

None.
