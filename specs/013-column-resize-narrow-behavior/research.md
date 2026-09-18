# Research: Architecture Panel Narrow-Width Layout

All items below were resolved directly from reading the existing implementation
(`frontend/src/components/workspace/ProviderArchitecturePanel.tsx`,
`frontend/src/components/ui/button.tsx`, `frontend/src/components/ui/scroll-area.tsx`,
`frontend/src/pages/WorkspacePage.tsx`); no external research was required. No
`NEEDS CLARIFICATION` markers remain from Technical Context.

## 1. Why does the Create button appear to get hidden when narrowing?

- **Decision**: Treat this as a flex-layout sizing problem in the create-form row, not a
  `display`/`visibility` bug. Give the input an explicit non-zero minimum width (e.g.
  `min-w-[3rem]`) instead of `min-w-0`, keep `flex-1`, and add `flex-wrap` to the form's row
  so that once the input has shrunk to that floor and the row still doesn't have room for
  the Create button beside it, the button wraps onto its own line directly under the input
  instead of overflowing the row.
- **Rationale**: The shared `Button` component already applies `shrink-0 whitespace-nowrap`
  to every button variant/size (`button.tsx` base class string), so the Create button
  itself never shrinks below its intrinsic content width — at the panel's absolute minimum
  resizable width (56px), the available inner content width (56px minus the `<aside>`'s
  `p-2` padding and the `<ul>`'s `pr-2` padding, roughly 32px) is smaller than the Create
  button's own intrinsic width. No amount of input-shrinking changes that: the button
  physically cannot sit beside any non-zero-width input at that extreme. Without
  `flex-wrap`, the row's un-shrinkable total width overflows its ancestors and gets clipped
  by the `<aside>`'s `overflow-hidden` (and/or scrolled out of view within the Radix
  `ScrollArea` viewport, which this row lives inside) — that clipping/scrolling-out is the
  reported "hidden button" symptom. Letting the row wrap converts that overflow into a
  second line: the button stays fully rendered and visible, just relocated below the input
  once space runs out, rather than clipped or requiring horizontal scroll.
- **Alternatives considered**: (a) Let the row overflow and rely on horizontal scroll —
  rejected, this is exactly the "hidden control" experience the spec calls out as the
  problem. (b) Shrink the Create button's own padding/font/label at narrow widths —
  rejected, spec explicitly wants the button to stay visible/usable as-is and only the
  entry field to narrow first; wrapping preserves the button unchanged and simply gives it
  a place to render. (c) Raise the panel's minimum resizable width so everything always
  fits on one line — rejected, spec says the existing collapse/expand and resize minimum
  behavior is "fine as-is" and out of scope.

## 2. How should action buttons (import, share, delete) stay visible?

- **Decision**: No change to the import button or its header row — the heading already
  wraps and a single `icon-xs` button (24px) comfortably fits the panel's smallest inner
  content width (~32px). For the per-architecture row (name + share + delete), removing
  `truncate` from the name button (item 3) and adding explicit `min-w-0` to it lets the
  name shrink/wrap instead of holding a fixed minimum width; additionally add `flex-wrap`
  to the row itself (`<li className="flex items-center gap-1">` →
  `flex flex-wrap items-start gap-1`), the same mechanism as item 1's create-form fix. This
  matters because the two fixed-size icon buttons together (`icon-sm`, 28px each, plus a
  4px gap = 60px) already exceed the panel's smallest inner content width (~32px) on their
  own, before the name is even considered — no amount of shrinking the name column closes
  that gap, so without `flex-wrap` the icons would still get clipped/scrolled out at the
  most extreme widths.
- **Rationale**: Confirmed via source read — the per-row `flex items-center gap-1` row has
  no `flex-wrap` today, so at widths where the two icon buttons plus even a zero-width name
  don't fit on one line, something must be clipped; wrapping keeps every control rendered
  and reachable by relocating the icons to their own line instead.
- **Alternatives considered**: Relying solely on the name shrinking to zero width without
  `flex-wrap` — rejected once the math showed two `icon-sm` buttons alone (60px) exceed the
  panel's minimum inner content width (~32px), so shrinking the name alone cannot prevent
  clipping at the extreme end; `flex-wrap` is necessary, not just cosmetic.

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
