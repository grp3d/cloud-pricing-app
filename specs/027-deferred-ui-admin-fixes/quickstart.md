# Quickstart: Validate 027 (Deferred UI and Admin Fixes)

## Prerequisites

- The dev stack from `docs/development.md`; no migration in this feature.
- `cd frontend && npm install` (adds `@axe-core/playwright`).
- For the icon check on real data: the local GCP and Azure snapshots, and the icon packages in
  `../images-web/` to re-run the generator.

## 1. Automated checks (free)

```bash
cd backend
uv run pytest tests/unit/test_icon_coverage.py tests/unit/test_icon_map_consistency.py
uv run pytest tests/contract/test_preferences.py tests/contract/test_admin_system_info.py
uv run pytest                                   # whole backend suite

cd ../frontend
npm test -- HeaderMenu UserMenu theme logOut SystemInformationSection
npx playwright test e2e/user-menu.spec.ts e2e/theme.spec.ts
npm test && npx playwright test                 # everything
```

Expected: all pass. tasks.md maps each acceptance scenario and success criterion to its test.
In short:
- the user menu's items for a guest and a user, and both menus from the keyboard (US1);
- the theme switches at once, persists for a user across reload, resets for a guest, and the
  server refuses a guest's theme (US2);
- every page passes the axe contrast scan in both themes (SC-002);
- Log in → Log out returns the guest's architectures; a missing guest ID gives a new guest; the
  unsaved-work prompt comes first (US3);
- each history state is shown, and an unreadable one shows Unavailable (US4);
- GCP and Azure icon issues list first-party services only, with one Marketplace count line,
  and the backend JSON maps equal the canvas's maps (US5).

## 2. Regenerate the GCP and Azure icon maps (once, when implementing)

```bash
cd backend
uv run python scripts/generate_provider_service_icon_map.py --provider gcp \
  --icons ../../images-web/gcp_architecture_icons
uv run python scripts/generate_provider_service_icon_map.py --provider azure \
  --icons ../../images-web/azure_architecture_icons
git diff --stat ../frontend/src/lib/   # expected: no change to the .generated.ts maps
```

The TypeScript maps must come out byte-identical (020, FR-010); only the new JSON files appear.

## 3. Manual walk-through: [MANUAL] items only

1. **The two menus look alike.** `[MANUAL: visual judgement]` Open the Cloud Pricing menu and
   the user menu one after the other, in both themes: same surface, spacing, hover and focus
   ring.
2. **Dark on real data.** `[MANUAL: legibility beyond measured contrast]` In the dark theme,
   open a GCP and an Azure architecture with icons, the Trends charts and the Agent tab with a
   comparison in the Results pane: everything is easy to read.
