# Quickstart: Validating 021 (Workspace Layout Redesign)

## Prerequisites

- Local Postgres (Homebrew `postgresql@18`) and the backend's `.env` as for development.
- `cd backend && uv sync --extra dev`, and `cd frontend && npm ci`.
- Playwright's Chromium: `cd frontend && npx playwright install chromium` (once).

## Automated checks

```bash
# Backend (preferences and importable tests are written first; see contracts/api.md)
cd backend && uv run pytest tests/contract/test_preferences.py -q && uv run pytest -q

# Frontend: types, lint, build, unit tests
cd frontend
npm run check-api-types      # needs the backend running on :8000
npm run lint && npm run build && npm test

# Browser checks: all 020 specs plus the new e2e/layout.spec.ts
npm run test:e2e
npx playwright show-report   # light/dark screenshots of each zone are attached
```

**Expected**: everything passes. The 020 specs (`price-change`, `icons`, `regression`) pass
with only `e2e/helpers.ts` changed (SC-009).

## Scenarios (by hand, or as automated in `e2e/layout.spec.ts`)

Start the app (`uv run uvicorn src.main:app` and `npm run dev`). Use one user with at least
one architecture in each of AWS, GCP and Azure.

### A. Header menu (US1)

1. Click the chevron beside "Cloud Pricing". Three groups (AWS, GCP, Azure) are listed, each
   with "New … architecture…" and "Import …".
2. Pick a GCP architecture. The menu closes, the GCP architecture opens, and the header
   reads "GCP · <name>".
3. "New Azure architecture…": type a name, then press Enter. The new Azure architecture
   opens. Escape in the name field clears it without closing the menu.
4. Make one public, then private. Delete one, confirm, and it is gone. If it was open, the
   workspace shows the empty prompt.
5. "Import a GCP architecture" lists only GCP public architectures of other users.
6. Go to Trends. Clicking "Cloud Pricing" returns to the workspace. The chevron opens the
   menu on Trends too, and picking a row opens that architecture in the workspace.
7. Using the keyboard only, do steps 1–4.

### B. Three zones and auto-front (US2)

1. At 1600×1000 the workspace shows the sidebar, canvas and inspector, and nothing else. The
   canvas is at least 900px wide.
2. Select a service on the canvas: the Service tab comes forward with its editor. Change
   vCPUs and Save: you stay on Service, and the price is marked out of date.
3. Click the Pricing tab, then Calculate. The new total and Price Change show.
4. On the Pricing tab choose "1 year" and click Calculate, then at once select a service so
   Service comes forward. When the calculation finishes, Pricing comes forward again. The
   same happens for the automatic calculation when an architecture without a stored result
   is opened.
5. Deselect (click empty canvas) with Service in front. Service stays in front, showing
   "Select a service on the canvas".
6. Collapse the inspector. Select a service: it expands with Service in front. Collapse it
   again and run a calculation (reopen the architecture): it stays collapsed, and the rail's
   Pricing button shows the new-result marker.

### C. Split, merge and swap (US3)

1. Drag the Service tab to the lower half. A drop zone shows, and on drop Pricing is above
   and Service below.
2. Drag the divider. Both panes resize, and neither goes below its minimum.
3. Drag Pricing (upper) to the lower half: the panes swap.
4. Drag the lower tab onto the upper tab bar: merged, with the dragged tab in front.
5. Start a drag and press Escape: nothing changes.
6. Reload. The arrangement and divider position are restored. Sign in on another browser
   profile as the same user: same arrangement.
7. Using the keyboard only, use "Service tab options" → "Move to lower half", then "Swap",
   then "Merge".

### D. Look and accessibility (US4)

1. Switch to dark: `document.documentElement.classList.add("dark")` in the console. Check
   the workspace, Trends, Admin and every dialog in light and dark. Only zinc greys and one
   blue accent appear, apart from status colours, provider logos and service icons.
2. Tab through the header, menu, sidebar, canvas items, tabs and inspector. Every control
   shows a visible focus ring, and hover and pressed states are visible.
3. Selected canvas box, service and connector: blue. Box borders are 1px, and connectors keep
   their arrow style.
4. At 1280×800 there is no horizontal page scroll, all three zones are usable, and the canvas
   is about 600px.
5. With macOS "Reduce motion" on, menus and panes appear without animation.
6. The theme contrast unit test passes (`npm test -- theme`).

### E. Regressions (FR-034)

Calculation, Price Change (020 A/B), icons (020 C), pop-out canvas, export and import (020
D), connectors and arrow styles, sharing, saved column widths for the sidebar and inspector.
The existing e2e specs cover the first five; check the rest by hand once.

## Results (2026-11-08, `/speckit-implement`)

**Automated, all passing:**
- Backend: 937 passed, 13 skipped (`uv run pytest -q`); `ruff check` clean. The new contract
  tests cover the `inspector` preference (5 cases) and `?provider=` on Import (3 cases).
- Frontend: `npm run lint` (7 warnings, all from before 021), `npm run build`, and 507 unit
  tests (48 files), including `theme.contrast.test.ts` (40 contrast checks in light and dark).
- API types: regenerated, and regenerating again gives no change.
- Browser: 16 passed, 1 skipped (`npm run test:e2e`). The three 020 specs pass with only
  `e2e/helpers.ts` changed (SC-009). The new `e2e/layout.spec.ts` automates:
  - **A:** every step except 4's public/private toggle (covered by the unit tests).
  - **B:** all steps except 4, the calculation that finishes after a selection.
  - **C:** all steps except the second browser profile in 6 (the reload is checked).
  - **D:** steps 1 and 4, with light and dark screenshots of the workspace, Trends and Admin
    in the report.

**Checked by looking at the screenshots:** zinc greys with one blue accent in both themes;
1px canvas boxes; at 1280px all three zones fit and the canvas is about 576px inside its
padding.

**Still to check by hand:**
- D2: tabbing through every control. Focus rings are in place app-wide through `index.css`,
  but no one has walked them.
- D3: a selected connector in blue, with each arrow style.
- D5: macOS "Reduce motion" on. The e2e emulates it for the screenshots only.
- C6: the same user on another browser profile.
- E: export, import and sharing by hand (the export/import and pop-out regressions are
  automated).
