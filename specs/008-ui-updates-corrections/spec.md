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
- Q: For Price Change (User Story 5), what counts as "the architecture has changed" — the
  trigger that lets the prior-total baseline update — and what happens if both the
  architecture and the Duration selection change together between two calculates? → A: Only
  edits to the architecture's own contents (adding/removing/editing a SKU selection,
  Collection, or Connector, or attaching/detaching a Connector's SKU) count as a change;
  changing Duration alone does not. When both change together, the system recalculates what
  the *prior* architecture (its state as of the last accepted calculation) would have cost
  at the *new* Duration, and compares that duration-adjusted prior total to the new actual
  total — so Price Change isolates the effect of the architecture edit alone, never
  conflating it with the effect of a Duration change. This recalculation MUST be a real,
  authoritative price lookup at the new duration (Constitution Principle I) — never a
  mathematical estimate/scaling of the old total, since duration doesn't scale pricing
  linearly (006: Reserved-term pricing in particular does not).
- Q: Does the Prior Calculation baseline (used for Price Change) need to survive a page
  reload, or is it acceptable for it to reset on every fresh load? → A: Persisted
  per-browser (`localStorage`, the same mechanism as column widths) — a reload keeps the
  Prior Calculation, so Price Change keeps working across reloads in the same browser.
- Q: Should the "Price per Sku" breakdown be sorted, or is any order acceptable? → A: Sorted
  by price, highest first — supports quickly spotting the biggest cost driver (SC-008).

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
Calculate again with no change (or only a Duration change); confirm the Price Change value
does not reset. Change the architecture and the Duration together, Calculate again; confirm
Price Change reflects only the architecture edit's effect, not the Duration change's own
effect on the total. Confirm a Price per Sku breakdown lists every priced SKU with its own
total.

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
   clicks Calculate again with no change to the architecture's own contents since the last
   calculation — whether nothing changed at all, or only the Duration selection changed —
   **Then** the Price Change value and arrow remain exactly what they were before this click
   (the prior-total baseline does not silently reset just because Calculate was clicked
   again, and a Duration-only change is not treated as an architecture change).
5. **Given** a prior calculation exists, **When** the user changes both the architecture's
   contents *and* the Duration selection before clicking Calculate again, **Then** the
   system recalculates the prior architecture's own contents at the new Duration to get a
   duration-adjusted comparison total, and the displayed Price Change reflects (new total −
   duration-adjusted comparison total) — isolating the effect of the architecture edit from
   the effect of the Duration change.
6. **Given** a calculated price, **When** the user views the pricing panel, **Then** a
   "Price per Sku" section appears below the main pricing results, separated by a visible
   divider, listing every priced SKU in the architecture with its own total price, sorted
   with the highest-cost SKU first.

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

### User Story 7 - Finding a service in search is faster and clearer (Priority: P2)

A user searching for an AWS service in column 2's "Add a Service" section needs to write
more powerful search patterns, see more results at once without losing track of the search
fields themselves while scrolling, know when there are more matches than are currently
shown, and see the results in a predictable order.

**Why this priority**: A direct usability improvement to an already-functional search
experience — valuable for anyone searching a large catalog, but the search already works
today without it.

**Independent Test**: In the "Add a Service" section, enter a regex pattern in each of the
three fields in turn and confirm matching results are returned; enter an invalid pattern and
confirm a clear, in-place error rather than a crash or silently empty results; scroll a long
result list and confirm the three fields stay in view; confirm up to 200 results can be
shown and, when more exist, a "(n of m results displayed)" note appears; confirm results are
sorted by the same text shown for each of them.

**Acceptance Scenarios**:

1. **Given** the "Add a Service" section, **When** the user types a regex pattern into the
   service code, product family, or search text field, **Then** results are filtered by
   that field matching the pattern (not only an exact or literal-substring match), for each
   of the three fields independently.
2. **Given** the user has typed a syntactically invalid regex pattern into one of the three
   fields, **When** results would otherwise be searched, **Then** a clear message appears
   next to that field explaining the pattern is invalid, and no broken or misleading results
   are shown.
3. **Given** a results list long enough to scroll, **When** the user scrolls it, **Then**
   the three filter fields remain visible and usable at the top of the section — only the
   results below them scroll.
4. **Given** a search that matches many services, **When** results are returned, **Then** up
   to 200 results are shown (raised from the current 50, matching the backend's existing
   maximum — no backend change needed for this part).
5. **Given** a search where more matching services exist than are currently displayed,
   **When** the user views the results, **Then** a "(n of m results displayed)" note is
   shown, where n is the number currently displayed and m is the total number that match;
   when every match is already displayed, no such note is shown. (Paging through the
   remaining results is explicitly out of scope for this feature — a later version.)
6. **Given** a set of search results, **When** the user views them, **Then** they are
   ordered by the same text shown for each result (the summary line already used today),
   not by an unrelated internal order.

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
- What happens to Price Change if the Duration selection changes but the architecture's own
  contents do not (User Story 5, FR-016)? The prior-total baseline is left exactly as it
  was — a Duration-only change never counts as "the architecture changed."
- What happens if both the architecture and Duration change together before the next
  Calculate (User Story 5, FR-016a)? The system recalculates the prior architecture's own
  contents at the new Duration to get a fair, duration-adjusted comparison point, rather
  than comparing totals computed at two different durations directly.
- What happens to Price Change (FR-016b) if browser storage is unavailable or was cleared
  (e.g., a private/incognito window)? The next Calculate behaves as if it were the first one
  ever for that Architecture — a total is shown with no Price Change, exactly as described
  in Acceptance Scenario 2 — rather than failing or showing an incorrect value.
- What happens to a deleted Architecture's stored Prior Calculation (FR-016b)? It becomes
  orphaned, unreachable data with no user-visible effect (the Architecture it was keyed to
  no longer exists to display it against); cleaning it up is an implementation housekeeping
  concern, not a user-facing behavior this spec constrains.
- What happens to the "(soon)" removal (User Story 3) given GCP/Azure still aren't
  implemented providers? The buttons remain disabled/non-functional exactly as they are
  today (007's behavior) — only the "(soon)" text is removed, not the disabled state.
- What happens when a search field (User Story 7) is left empty? An empty field is not a
  pattern to evaluate — it behaves exactly as it does today (that field simply isn't used to
  filter), not as a regex that matches everything.
- What happens when a regex pattern in one field (User Story 7) matches zero services? The
  existing "No matching services found." state is shown, the same as any other search with
  no matches today — this is not treated as an error.
- What happens to the "(n of m results displayed)" note (User Story 7) when a search's
  filters are broad enough that determining the exact total is expensive? The total shown is
  still the true total, not an estimate or a capped placeholder (Constitution Principle I) —
  performance of computing it is an implementation concern, not a reason to show an
  inaccurate count.

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
  Architecture and the architecture's own contents have changed since that prior
  calculation (per FR-016's definition of "changed"), the system MUST show a "Price Change"
  value equal to (new total − comparison total), with a red upward indicator when positive,
  a green downward indicator when negative, and no indicator when zero. "Comparison total"
  is the prior total itself, unless the Duration selection has also changed since the prior
  calculation (FR-016a), in which case it is the duration-adjusted prior total.
- **FR-016**: Only a change to the architecture's own contents — adding, removing, or
  editing a SKU selection; adding or removing a Collection or Data Connector; or
  attaching/detaching a Connector's SKU — counts as the architecture having "changed" for
  Price Change purposes. Changing the Duration selection alone, with no other edit, does
  NOT count as a change: clicking Calculate again after only changing Duration (or after no
  change at all) MUST leave the existing Price Change value and its prior-total baseline
  exactly as they were.
- **FR-016a**: When the architecture's contents *and* the Duration selection have both
  changed since the prior calculation, the system MUST derive the "comparison total" (FR-015)
  by recalculating the *prior* architecture's contents (its state as of the last accepted
  calculation) at the *new* Duration, using the same authoritative pricing calculation used
  for any other price (Constitution Principle I) — never by mathematically scaling or
  estimating the old total, since price does not scale linearly with duration in general
  (006: Reserved-term pricing in particular does not).
- **FR-016b**: The Prior Calculation (FR-015/016/016a) MUST persist per-browser (same
  mechanism as column widths, FR-013), keyed by Architecture, so that reloading the page
  does not lose the baseline Price Change depends on.
- **FR-017**: The pricing panel MUST show a "Price per Sku" section, visually separated from
  the main result, listing every priced SKU in the Architecture together with that SKU's
  own total price, sorted by that price highest-first (Clarifications) so the biggest cost
  driver is always at the top.

**Visual style (User Story 6)**

- **FR-018**: Application-wide text size MUST be reduced by one Tailwind text-size step
  (Clarifications — not the literal 70% figure from the source notes), applied consistently
  across every panel.
- **FR-019**: The application's color theme MUST be rebuilt on Radix's "sky" color scale as
  adopted through shadcn/ui, applied consistently across every panel, with the same
  diagram-internals exception already established in 007 (FR-009/SC-004).

**Service search (User Story 7)**

- **FR-020**: Each of the three "Add a Service" filter fields (service code, product family,
  search text) MUST independently support the user entering a regex pattern, matched against
  that field's corresponding data, rather than only an exact or literal-substring match.
- **FR-021**: An invalid regex pattern in any of the three fields MUST produce a clear,
  in-place validation message next to that field, and MUST NOT produce a crash, an
  unrelated error, or a silently-empty/misleading result set.
- **FR-022**: Within the "Add a Service" section, the three filter fields MUST stay fixed in
  view while the results list beneath them scrolls independently — this mirrors 007's
  FR-004 fixed-top-controls pattern, applied to this section's own fields.
- **FR-023**: A search MUST return up to 200 results (raised from the current 50, matching
  the backend catalog search's existing maximum).
- **FR-024**: When the number of matching results exceeds the number displayed, the search
  MUST show a "(n of m results displayed)" indicator (n = displayed count, m = true total
  matching count); when every match is displayed, no such indicator is shown. Paging through
  the remainder is explicitly out of scope for this feature.
- **FR-025**: Search results MUST be sorted alphabetically (ascending) by the same text
  displayed to the user for each result (the existing summary line), rather than today's
  underlying data order.

### Key Entities

- **Column width preference**: a per-column width value the user has chosen by dragging a
  boundary; persists per-browser (Clarifications).
- **Prior Calculation**: the most recently "locked in" calculation for a given Architecture
  — its resulting total, the Duration it was calculated at, and enough of the architecture's
  own state (its SKU selections and their inputs) to re-run that same calculation at a
  different Duration later. Used as the baseline for the next Price Change (FR-015); updates
  only when the architecture's own contents have changed since it was last set (FR-016), and
  is itself recalculated at a new Duration, rather than replaced, when only Duration changed
  alongside a content change (FR-016a). Persists per-browser, keyed by Architecture, so it
  survives a page reload (FR-016b).
- **Price per Sku entry**: a derived, display-only pairing of a SKU Selection to its own
  contribution to the Architecture's total price — not a new stored entity, computed at
  calculation time from data the pricing calculation (004/006) already produces.
- **Search match total**: the true count of catalog services matching the current search
  filters, independent of how many are actually displayed (FR-024) — derived at search
  time, not stored.

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
  Change value exactly matches (new total − comparison total) to the cent, with the correct
  direction indicator — including when a Duration change accompanied the architecture
  change, where the comparison total is the duration-adjusted prior total (FR-016a), not
  the original prior total.
- **SC-008**: A user can identify the highest-cost individual SKU in an architecture in
  under 10 seconds using the Price per Sku breakdown, without needing to inspect each
  service individually.
- **SC-009**: A user can express a search filter today's exact/literal matching can't (e.g.,
  "any instance type starting with r7") using a regex pattern in any of the three search
  fields, and get correct results.
- **SC-010**: When a search has more matches than are displayed, 100% of the time the user
  is shown accurately how many total matches exist, not just how many are on screen.

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
- Today, the service-code and product-family search fields match exactly, and only the free
  -text field does a substring match — regex support (FR-020) changes all three fields to
  pattern-based matching, which is a strictly more permissive behavior than today's, not a
  narrower one; existing plain-text searches keep working, since ordinary text is itself a
  valid literal regex pattern. Regex matching is case-insensitive, consistent with today's
  free-text field.
- Determining the true total match count (FR-024, "m" in "n of m") is new: today's search
  only signals "the returned page was full, so there might be more," not an exact total —
  computing an exact total requires the backend catalog search to run an additional query.
  This is this feature's one backend touch-point; the 200-result cap (FR-023) itself needs
  no backend change, since it exactly matches the backend catalog search's existing maximum.
