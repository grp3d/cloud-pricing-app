# Feature Specification: UI Updates and Corrections

**Feature Branch**: `008-ui-updates-corrections`

**Created**: 2026-09-10

**Status**: Draft

**Input**: User description: "UI updates and corrections" (detailed in `docs/functionality_2026-09-10.md`)

## Clarifications

### Session 2026-09-10

- Q: Is a rewrite of the diagram panel's implementation in scope for this feature if the
  listed bugs turn out to need one, or should this feature stick to fixing the specific
  symptoms on top of the existing approach? → A: Rewrite is in scope if the planning phase
  concludes it's needed.
- Q: Should saved column widths be per-browser (`localStorage`, no backend change) or
  follow a user across devices (backend-persisted)? → A: Per-browser (`localStorage`).
- Q: The source notes say "reduce font sizes by 70%" — read literally that's near-unreadable.
  What's the actual target? → A: One Tailwind text-size step down everywhere (e.g.
  `text-sm` → `text-xs`), not the literal 70% figure.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The architecture diagram renders reliably and can use the space it's given (Priority: P1)

A user assembling an architecture needs the diagram to behave predictably: boxes should be
resizable by hand when the default size doesn't suit them, boxes should always be tall
enough to show their own text without clipping, clicking empty space inside a VPC should
never break the view, and the whole diagram panel should be able to grow well beyond its
current cramped default when the user wants more room to work.

**Why this priority**: The diagram is the visual center of the tool (column 4 of 5). A
diagram that can lose all its content from a single misclick, or that permanently clips a
box's own label, undermines trust in the whole application — this is corrective, not
cosmetic, work.

**Independent Test**: Open an Architecture with at least one VPC containing a nested
Application Component and several services. Manually resize a box by dragging its handle;
add enough services to a box that its default size would once have clipped text; click an
empty area inside the VPC's box; drag the diagram panel's resize handle. Each of these
actions produces the expected visual result with no page reload required. A rewrite of the
diagram panel's implementation is in scope for this story if the planning phase concludes
the existing approach can't reliably satisfy it (Clarifications) — the acceptance scenarios
below describe the required *behavior*, not a constraint to patch the current code as-is.

**Acceptance Scenarios**:

1. **Given** any box (Application Component or VPC) on the diagram, **When** the user drags
   that box's resize handle, **Then** the box takes on the new size and keeps it for the
   rest of the session.
2. **Given** a box whose services and label would not fit at its current size, **When** the
   box is rendered (on load, or immediately after a service is added/removed), **Then** the
   box is tall enough to show every line of its own content without clipping or needing a
   scrollbar.
3. **Given** a VPC box containing one or more nested Application Components, **When** the
   user clicks an empty area inside the VPC box (not on a nested box, not on the VPC's own
   label), **Then** the diagram remains fully visible and interactive — nothing disappears,
   and no page reload is needed.
4. **Given** the architecture diagram panel at its default size, **When** the user drags its
   resize handle, **Then** the panel can grow to occupy substantially more of the window's
   available height than its current ceiling allows.

---

### User Story 2 - Column 3 stays visible, and columns 1 through 3 collapse the same way (Priority: P1)

A user needs the five-column layout to feel stable rather than shifting content sideways
every time a service is selected or deselected, and needs the same collapse/expand control
available on columns 1, 2, and 3 — not only column 1 — for whichever column is temporarily
in their way.

**Why this priority**: Column 3 disappearing and reappearing shifts every column to its
right, which is disorienting during normal use; this is a correction to a decision made in
the prior UI overhaul (007), made after living with it. Consistent collapsibility is a
direct, low-risk extension of an already-shipped pattern.

**Independent Test**: With an Architecture open, select and then deselect a service, a
Collection, and a Connector in turn, confirming column 3's presence and width never change.
Separately, collapse and expand columns 1, 2, and 3 each via their own icon.

**Acceptance Scenarios**:

1. **Given** an open Architecture, **When** no service is selected (nothing selected at
   all, or a Collection/Connector/VPC is selected that isn't a service), **Then** column 3
   is still shown, at its normal width, simply with no content in it (or a minimal
   placeholder) — it does not collapse to zero width.
2. **Given** any of columns 1, 2, or 3 in its expanded state, **When** the user clicks that
   column's collapse icon (top-right corner), **Then** the column collapses to its icon-only
   rail, matching column 1's existing collapsed behavior (research.md decisions from 007
   still apply: icons with hover tooltips, every action remains reachable).
3. **Given** any of columns 1, 2, or 3 in its collapsed state, **When** the user clicks its
   expand icon, **Then** the column returns to its normal expanded width and content.

---

### User Story 3 - Each column's structure and labels are self-explanatory (Priority: P2)

A user should be able to tell what a column is for, and what each of its sections is for,
from the labels alone — including telling apart an empty section from a section that simply
doesn't exist right now.

**Why this priority**: This is a clarity/labeling pass on top of the already-functional
007 layout — valuable, but the application is fully usable without it, unlike User Stories
1 and 2.

**Independent Test**: With column 1 collapsed, confirm each provider is shown as its own
distinct icon with a name on hover. With an Architecture open, confirm column 2 and column
3 each show the specified header and section names, and that column 2's section boundaries
(separators) are visible even when a section between them has no content.

**Acceptance Scenarios**:

1. **Given** column 1 in its expanded state, **When** the user views the provider list,
   **Then** each provider (AWS, GCP, Azure) is on its own line, and GCP/Azure no longer show
   "(soon)" text.
2. **Given** column 1 in its collapsed state, **When** the user views the provider icons,
   **Then** each provider is represented by that provider's own logo/icon (not a generic
   placeholder icon).
3. **Given** column 2 with an Architecture open, **When** the user views the column,
   **Then** its header reads "Architecture Editor"; its three sections are labeled
   "Collections" (creation controls + Connect/Remove Connector — unchanged from 007's
   FR-004 fixed-top behavior), "Selected Collection" (the current Collection's/Connector's
   own name and delete control), and "Add a Service" (the search panel); and a visible
   separator appears between each pair of adjacent sections, present even when the section
   between two separators is currently empty.
4. **Given** column 3 with or without a service selected, **When** the user views the
   column, **Then** its header reads "Service Editor".

---

### User Story 4 - Column widths can be adjusted and are remembered (Priority: P2)

A user working with a particular kind of Architecture (e.g., one with long service names,
or one where the diagram needs more horizontal room) should be able to drag the boundary
between any two adjacent columns to resize them, and have that sizing still be in place the
next time they use the application.

**Why this priority**: A real quality-of-life improvement for repeat use, independent of
every other story here — but the application remains fully functional at fixed widths, so
it ranks below the corrections and structural fixes above.

**Independent Test**: Drag the boundary between two columns to a new position; reload the
page in the same browser; confirm the resized widths are still in effect. Widths persist
per-browser (`localStorage`, Clarifications) — they are not expected to follow the user to
a different browser or device.

**Acceptance Scenarios**:

1. **Given** two adjacent columns, **When** the user drags the vertical boundary between
   them, **Then** both columns' widths update live to follow the drag, within reasonable
   minimum-width limits that keep every column usable.
2. **Given** the user has resized one or more columns, **When** the user returns to the
   application later, **Then** the columns render at the widths the user last set, not the
   application's default widths.

---

### User Story 5 - Pricing results are precise and show what changed (Priority: P2)

A user calculating a price needs the numbers to be clean (no long decimal remainders), and
needs to be able to tell, at a glance, whether their latest change to the architecture made
it more or less expensive than before — and to see which individual services are driving
the total.

**Why this priority**: This turns the pricing panel from "a number" into a decision-support
tool, which is valuable but additive — existing pricing accuracy (006) and display (007) are
untouched by not doing this.

**Independent Test**: Calculate a price; confirm the total (and every other displayed
price) is rounded to 2 decimal places. Change the architecture (e.g., add a service),
Calculate again; confirm a Price Change value and directional arrow appear and are correct.
Calculate again with no change; confirm the Price Change value does not reset. Confirm a
Price per Sku breakdown lists every priced SKU with its own total.

**Acceptance Scenarios**:

1. **Given** any calculated price (the total, or any other price shown in the pricing
   panel), **When** it is displayed, **Then** it is rounded to exactly 2 decimal places.
2. **Given** a user has never clicked Calculate before for this architecture, **When** they
   click Calculate for the first time, **Then** a total is shown and no Price Change value
   is shown yet (there is nothing to compare against).
3. **Given** a prior calculated total exists and the architecture has changed since that
   calculation, **When** the user clicks Calculate, **Then** a Price Change field appears
   below the total showing (new total − prior total); a red upward arrow appears beside it
   if the price increased, a green downward arrow if it decreased, and no arrow if it is
   unchanged; and the "prior total" baseline used for the *next* comparison updates to this
   new total.
4. **Given** a prior calculated total and Price Change already exist, **When** the user
   clicks Calculate again with no architecture change since the last calculation, **Then**
   the Price Change value and arrow remain exactly what they were before this click (the
   "prior total" baseline does not silently reset to the current total just because
   Calculate was clicked again).
5. **Given** a calculated price, **When** the user views the pricing panel, **Then** a
   "Price per Sku" section appears below the main pricing results, separated by a visible
   divider, listing every priced SKU in the architecture with its own total price.

---

### User Story 6 - A smaller, colored visual style (Priority: P3)

A user should see a more compact, colored interface rather than today's neutral,
comparatively large-type design.

**Why this priority**: Purely cosmetic — every other capability in the application is
identical whether or not this story ships.

**Independent Test**: Compare font sizes and color usage across the application before and
after. Text is one Tailwind text-size step smaller everywhere (e.g. `text-sm` → `text-xs`,
`text-base` → `text-sm`), not the literal 70% reduction the source notes stated
(Clarifications).

**Acceptance Scenarios**:

1. **Given** any text in the application, **When** compared to its current size, **Then**
   it renders one Tailwind text-size step smaller, applied consistently across every panel.
2. **Given** any themed element (buttons, panels, active/selected states, links), **When**
   viewed, **Then** it draws its color from Radix's "sky" color scale as adopted through
   shadcn/ui's theming, replacing the current neutral palette, consistently across every
   panel (the diagram's own node/edge rendering keeps the exception already established in
   007/FR-009 where forcing shared styling there would add complexity rather than reduce
   it).

---

### Edge Cases

- What happens to a box's resize state (User Story 1) if that box is deleted and a new box
  is later added in its place? The new box gets its own default/auto-fit size — resize
  state is not something that persists per Collection identity across a delete/re-add.
- What happens to column 3 (User Story 2) when the Architecture itself is deleted while a
  service is selected? It still stays visible and reduces to its blank state, consistent
  with every other panel's reset-on-delete behavior from 007 (FR-013).
- What happens if the user drags a column (User Story 4) narrower than its usable minimum?
  The drag is clamped at a minimum width rather than allowing a column to shrink to
  uselessness or zero.
- What happens to Price Change (User Story 5) if the user switches to a different
  Architecture and back? Each Architecture tracks its own prior-total baseline
  independently — switching away and back does not fabricate a change that didn't happen,
  nor does it carry one Architecture's baseline into another's.
- What happens to Price Change if a SKU becomes unpriceable (already-handled case from 006)
  between two calculations? The total used for both the current and prior values is the
  same "priced total" already shown today (excluding unpriceable items, per 006); the
  Price Change reflects the difference in that same total.
- What happens to the "(soon)" removal (User Story 3) given GCP/Azure still aren't
  implemented providers? The buttons remain disabled/non-functional exactly as they are
  today (007's behavior) — only the "(soon)" text is removed, not the disabled state.

## Requirements *(mandatory)*

### Functional Requirements

**Diagram reliability and sizing (User Story 1)**

- **FR-001**: Every box on the architecture diagram (Application Component and VPC) MUST be
  individually resizable by the user dragging a resize handle, and MUST retain the
  user-set size for the remainder of the session.
- **FR-002**: Every box on the architecture diagram MUST be tall enough to display its own
  label and full service list without clipped text, whenever it is rendered or re-rendered
  after its content changes — this MUST hold in normal use, not only under the specific
  conditions previously verified in 007 (see `005-box-autoresize-not-observed` memory: this
  requirement was not reliably met after 007 and needs re-verification, not an assumption
  of prior success).
- **FR-003**: Clicking empty space inside a VPC box's own area (not on a nested box, not on
  the VPC's label) MUST NOT cause the diagram or any other part of the application to
  disappear or become unusable; no action a user takes on the diagram may require a page
  reload to recover from.
- **FR-004**: The architecture diagram panel MUST be resizable (via its existing
  bottom-right drag handle from 005, or an equivalent control) to occupy substantially more
  of the window's available height than its current default ceiling.

**Column visibility and collapsibility (User Story 2)**

- **FR-005**: Column 3 (service configuration) MUST always be present and occupy its normal
  width, regardless of what is selected — this supersedes 007's FR-012, which required
  column 3 to collapse to zero width when nothing was selected. When no service is
  selected, column 3 MUST show no content, or a minimal placeholder, rather than a full
  service editor.
- **FR-006**: Columns 1, 2, and 3 MUST each provide their own collapse/expand icon control
  in the column's top-right corner, functioning the same way column 1's existing
  collapse/expand control does today (icon-only rail when collapsed, hover reveals full
  labels, every action remains reachable by icon) — this extends 007's FR-016/FR-017 from
  column 1 alone to columns 1-3.

**Column and section labeling (User Story 3)**

- **FR-007**: In column 1's expanded state, each cloud provider (AWS, GCP, Azure) MUST be
  shown on its own line, and the "(soon)" text MUST no longer appear next to GCP or Azure.
- **FR-008**: In column 1's collapsed state, each provider MUST be represented by that
  provider's own icon/logo, not a generic placeholder icon.
- **FR-009**: Column 2's header MUST read "Architecture Editor", and its three sections
  MUST be labeled "Collections", "Selected Collection", and "Add a Service" respectively
  (renaming, not restructuring, 007's existing fixed-top-controls / selection / search
  layout).
- **FR-010**: Column 2 MUST show a visible separator between each pair of adjacent
  sections, and that separator MUST remain visible even when the section it borders has no
  content to show.
- **FR-011**: Column 3's header MUST read "Service Editor".

**Adjustable, persistent column widths (User Story 4)**

- **FR-012**: Every column boundary MUST be draggable by the user to resize the two
  adjacent columns, subject to a reasonable per-column minimum width.
- **FR-013**: Column widths MUST persist per-browser (Clarifications) so a returning user in
  the same browser sees their chosen widths without re-configuring them; this persistence
  is not required to follow a user across different browsers or devices.

**Pricing display (User Story 5)**

- **FR-014**: Every price value displayed anywhere in the pricing panel (the total, and any
  future or existing per-item price) MUST be rounded to exactly 2 decimal places for
  display.
- **FR-015**: After a Calculate action, if a prior calculated total exists for the current
  Architecture and the architecture has changed since that prior calculation, the system
  MUST show a "Price Change" value equal to (new total − prior total), with a red upward
  indicator when positive, a green downward indicator when negative, and no indicator when
  zero.
- **FR-016**: The "prior total" baseline used for Price Change MUST only be updated to a new
  value when the Architecture has actually changed since it was last set — clicking
  Calculate again with no intervening change MUST leave the existing Price Change value and
  baseline exactly as they were.
- **FR-017**: The pricing panel MUST show a "Price per Sku" section, visually separated from
  the main result, listing every priced SKU in the Architecture together with that SKU's
  own total price.

**Visual style (User Story 6)**

- **FR-018**: Application-wide text size MUST be reduced by one Tailwind text-size step
  (Clarifications — not the literal 70% figure from the source notes), applied consistently
  across every panel.
- **FR-019**: The application's color theme MUST be rebuilt on Radix's "sky" color scale as
  adopted through shadcn/ui, applied consistently across every panel, with the same
  diagram-internals exception already established in 007 (FR-009/SC-004).

### Key Entities

- **Column width preference**: a per-column width value the user has chosen by dragging a
  boundary; persists per the Clarifications answer below.
- **Prior Total**: the most recently "locked in" calculated total for a given Architecture,
  used as the baseline for the next Price Change; updates only when the Architecture has
  changed since it was last set (see FR-016).
- **Price per Sku entry**: a derived, display-only pairing of a SKU Selection to its own
  contribution to the Architecture's total price — not a new stored entity, computed at
  calculation time from data the pricing calculation (004/006) already produces.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero user actions on the architecture diagram (including clicking empty space
  inside a VPC) require a page reload to recover a working view.
- **SC-002**: 100% of boxes on the diagram display their full label and service list with no
  clipped text, across architectures ranging from a single service to a deeply nested VPC
  with many services.
- **SC-003**: A user can resize the diagram panel to at least double its current default
  height ceiling.
- **SC-004**: A first-time user can correctly state the purpose of each of columns 2 and 3
  from their header and section labels alone, without instructions.
- **SC-005**: A returning user's column widths and collapse states are exactly as they left
  them, with zero manual re-configuration, on every subsequent visit in the same browser.
- **SC-006**: 100% of displayed prices show exactly 2 decimal places, with no long
  floating-point remainders visible anywhere in the pricing panel.
- **SC-007**: After any architecture change followed by a Calculate, the displayed Price
  Change value exactly matches (new total − prior total) to the cent, with the correct
  direction indicator.
- **SC-008**: A user can identify the highest-cost individual SKU in an architecture in
  under 10 seconds using the Price per Sku breakdown, without needing to inspect each
  service individually.

## Assumptions

- Per Clarifications, whether User Story 1's diagram fixes are implemented as targeted
  patches or a fuller rewrite of the diagram panel is a planning-phase decision, not fixed
  here — this spec defines the required end-user behavior (FR-001 through FR-004) either
  way.
- The three provider icon images referenced in `docs/functionality_2026-09-10.md`
  (`screenshot-samples/{gcp,aws,azure}_icon.png`) are the intended assets for FR-008; as of
  this writing, `gcp_icon.png` and `azure_icon.png` exist in that directory but
  `aws_icon.png` does not — it must be supplied before FR-008 can be implemented for AWS.
- "Rounded to 2 decimal places" (FR-014) is a display-only change — the underlying
  calculation precision and the values sent to/from the backend are unaffected; only how a
  price is formatted for on-screen display changes.
- The existing 007 empty/prompt-state behavior for columns 2, 4, and 5 (shown when no
  Architecture is selected) is unaffected by this feature except where an FR above says
  otherwise; column 3's new always-visible behavior (FR-005) applies in that no-Architecture
  state too — it shows its normal blank/placeholder state rather than collapsing.
- "Minimum width" per column (FR-012) is left to implementation to choose a value that keeps
  every column's own controls usable (e.g., enough for column 1's icon rail, column 5's
  duration selector) — not spelled out as an exact pixel value here.
- Reducing font size (FR-018) and adopting the sky color scale (FR-019) apply to this
  application's own UI only; nothing about vendor pricing data, its precision, or its
  presentation format changes.
