# Research: Architecture Panel Narrow-Width Layout

All items below were resolved directly from reading the existing implementation
(`frontend/src/components/workspace/ProviderArchitecturePanel.tsx`,
`frontend/src/components/ui/button.tsx`, `frontend/src/components/ui/scroll-area.tsx`,
`frontend/src/pages/WorkspacePage.tsx`); no external research was required. No
`NEEDS CLARIFICATION` markers remain from Technical Context.

## 1. Why does the Create button appear to get hidden when narrowing?

- **Decision**: Treat this as a flex-layout sizing problem in the create-form row, not a
  `display`/`visibility` bug. Fix it by making sure the row's minimum required width never
  exceeds the panel's available width — i.e., the name input (already `flex-1 min-w-0`)
  keeps absorbing all the shrinkage, and the Create button's existing fixed intrinsic size
  is preserved end-to-end so it's always the last thing to run out of room, never the
  first.
- **Rationale**: The shared `Button` component already applies `shrink-0 whitespace-nowrap`
  to every button variant/size (`button.tsx` base class string), so the Create button
  itself never shrinks below its intrinsic content width today. The input already has
  `min-w-0 flex-1`, so it already shrinks first in principle. The reported "hidden" symptom
  therefore isn't the button's own flexbox shrink behavior — it's that once the row's
  combined minimum width (shrunk input + fixed button) exceeds the panel's inner content
  width, the surrounding `<aside>` (`overflow-hidden`, fixed pixel `width`) and the Radix
  `ScrollArea` viewport clip/scroll horizontally rather than reflowing, so the button can
  end up scrolled out of the visible area at the panel's narrowest widths. The concrete fix
  is to guarantee the row itself never needs more width than the panel provides: give the
  input an explicit small minimum (so it never disappears entirely) and verify no ancestor
  introduces horizontal scroll for this row at the panel's minimum resizable width (56px,
  the same as the collapsed-rail width) plus its `p-2` padding.
- **Alternatives considered**: (a) Let the row overflow and rely on horizontal scroll —
  rejected, this is exactly the "hidden control" experience the spec calls out as the
  problem. (b) Shrink the Create button's own padding/font at narrow widths — rejected,
  spec explicitly wants the button to stay visible/usable as-is and only the entry field to
  narrow first.

## 2. How should action buttons (import, share, delete) stay visible?

- **Decision**: No layout change is needed for the import button (header row) or the
  per-row share/delete icon buttons themselves — `icon-xs`/`icon-sm` buttons are fixed
  `size-*` squares with `shrink-0` already applied by the shared `Button` component, so
  they don't shrink. The only thing that must change is the *other* element sharing each
  row with them: the heading text (already wraps, no change needed) and the architecture
  name button (currently `truncate`, see item 3) so that the fixed-size icon buttons are
  never pushed out of the visible/scrollable width by a sibling that refuses to shrink or
  wrap.
- **Rationale**: Confirmed via source read — `justify-between` header row and per-row
  `flex items-center gap-1` rows have no `flex-wrap`, so if every sibling in the row can
  shrink or wrap to fit, the fixed-size icon buttons stay visible without any change to the
  buttons themselves.
- **Alternatives considered**: Wrapping the button row itself (`flex-wrap`) so icons drop
  to a second line — rejected as unnecessary once the name element shrinks/wraps instead of
  fighting the icons for space, and it would visually reorder controls in a way the spec
  doesn't ask for.

## 3. How should architecture names word-wrap instead of truncating?

- **Decision**: Remove `truncate` from the architecture-name `Button` (line ~204) and
  replace it with wrapping-friendly classes (`whitespace-normal` to override the shared
  `Button` component's base `whitespace-nowrap`, plus `text-left` / a break rule such as
  `break-words` for long unbroken names) and change the row's alignment from
  `items-center` to `items-start` so a multi-line wrapped name aligns naturally with the
  fixed-size icon buttons next to it instead of vertically centering against a taller
  block.
- **Rationale**: This directly mirrors how the sibling `<h3>` heading already wraps (no
  `truncate`/`whitespace-nowrap` set on it), which is the exact reference behavior the spec
  asks to match. `Button`'s base class sets `whitespace-nowrap` for every variant, so an
  explicit override is required on this specific button to allow wrapping.
- **Alternatives considered**: Adding a tooltip/title showing the full name on hover while
  keeping truncation — rejected, spec explicitly asks for visible wrapped text, not a
  hover-only affordance, and a tooltip already exists for other purposes on this row.
