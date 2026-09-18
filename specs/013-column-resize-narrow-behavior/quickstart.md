# Quickstart: Validate Architecture Panel Narrow-Width Layout

## Prerequisites

- Repo checked out on branch `013-column-resize-narrow-behavior`
- Frontend dependencies installed (`cd frontend && npm install`, if not already done)

## Automated check

```bash
cd frontend
npm test -- ProviderArchitecturePanel
```

Expected: the new/updated tests in
`frontend/src/components/workspace/ProviderArchitecturePanel.test.tsx` pass, covering:

- Create button remains present (not `display: none`, not scrolled/clipped out) when the
  panel is rendered at the minimum resizable width (56px).
- Import, per-row share, and per-row delete buttons remain present at the minimum
  resizable width.
- A long architecture name renders without the `truncate` ellipsis class/behavior at a
  narrow width, i.e. its full text is present in the DOM and wraps rather than being
  clipped.

## Manual browser validation

1. Start the frontend dev server: `cd frontend && npm run dev` (and the backend per its own
   run instructions if pricing data / architectures are needed for a realistic list).
2. Open the app, log in (or continue as guest), and land on the workspace/cloud pricing
   tab so column 1 (the `ProviderArchitecturePanel`) is visible on the left.
3. Create at least one architecture with a long name (long enough to overflow the panel's
   default width), so wrapping behavior is observable.
4. Grab column 1's right-edge resize handle and drag it left, narrowing the panel in small
   increments down to its minimum width.
5. **Confirm, throughout the drag**:
   - The "New Architecture name" input visibly shrinks in width before the Create button
     changes size, position, or visibility at all.
   - The Create button stays fully visible and clickable at every width, including the
     minimum.
   - The import button (top of the Architectures section) stays fully visible and
     clickable at every width.
   - Each listed architecture's share and delete icon buttons stay fully visible and
     clickable at every width.
   - The long architecture name wraps onto additional lines (matching how the
     "<PROVIDER> Architectures" heading already wraps) instead of showing `…` or being cut
     off.
6. Confirm collapse/expand (the panel-toggle button) still works exactly as before at any
   width reached during the drag — this feature must not change that behavior.
7. Widen the panel back out and confirm the input, buttons, and list return to their normal
   full-width layout with no leftover visual artifacts from the narrow state.

## Expected outcome

All checks in step 5 hold at every width from the panel's default down to its minimum
(56px) — no action button is ever hidden, clipped, or requires horizontal scrolling to
reach, and no architecture name is ever shown with a truncating ellipsis.
