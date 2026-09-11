# Feature Specification: UI Fixes and Enhancements — Next Iteration

**Feature Branch**: `009-ui-fixes-next-iteration`

**Created**: 2026-09-11

**Status**: Draft

**Input**: User description: "Based on docs/functionality_2026-09-11.md, create a new feature spec for the next iteration of UI fixes and enhancements." The source document lists bug-fix Issues and new-functionality Updates spanning the five-column workspace (column 2 = Architecture Editor, column 4 = Architecture Diagram, column 5 = Pricing), covering: a SKU that fails to price, a connector/service data-model correction, two architecture-diagram blank-screen bugs, a price-change duration-adjustment bug, a service-search coverage indicator, pricing display formatting, architecture-diagram styling and persistence, an explicit "Add Connector" control, and AWSDataTransfer-specific filtering and display.

## Clarifications

### Session 2026-09-11

- Q: When a user clicks the new "Add Connector" button, how do they pick the two Collections to connect? → A: Open a dialog with "From Collection" / "To Collection" dropdowns, populated with all Application Components and VPCs, then confirm.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A specific SKU prices successfully (Priority: P1)

A user adds instance SKU `2AB37QDFJZBGQ5YP` to an Architecture and calculates its price. Today this fails; the user needs it to price like any other valid SKU.

**Why this priority**: An unpriceable SKU that should be priceable is a core correctness failure — it directly contradicts the product's reason to exist (accurate pricing).

**Independent Test**: Add SKU `2AB37QDFJZBGQ5YP` to an Architecture, run a calculation, and confirm it returns a price rather than an error or an "unpriceable" entry.

**Acceptance Scenarios**:

1. **Given** an Architecture with SKU `2AB37QDFJZBGQ5YP` selected, **When** the user calculates price, **Then** the calculation succeeds and the SKU contributes a price to the total (or, if it is genuinely unpriceable due to missing vendor pricing data, the system reports that clearly rather than failing the whole calculation).

---

### User Story 2 - Price Change reflects a duration-only adjustment (Priority: P1)

A user has an established Prior Calculation baseline. Without changing the architecture's contents, the user switches the pricing Duration (e.g., from 1 month to 1 year). Price Change must scale to the new duration rather than staying frozen at the old duration's value or disappearing.

**Why this priority**: Price Change is the headline comparison metric (column 5); showing a stale or wrong value after a duration switch is a correctness bug in the app's primary value proposition.

**Independent Test**: Establish a baseline at 1 month, note the Price Change value, switch Duration to 1 year with no other edits, and confirm Price Change updates to the duration-adjusted value (i.e., proportional to the duration ratio between the two supported durations) rather than remaining unchanged.

**Acceptance Scenarios**:

1. **Given** a Prior Calculation baseline established at 1 month with Price Change showing some amount **X**, **When** the user switches Duration to 1 year without changing any selection, **Then** Price Change updates to reflect the same underlying change at the 1-year duration (proportional to the 1-month-to-1-year ratio), and the baseline is understood to have been evaluated at the new duration.
2. **Given** the same scenario, **When** the user switches Duration back to 1 month, **Then** Price Change returns to its original 1-month value.

---

### User Story 3 - The architecture diagram stays visible during normal editing (Priority: P1)

A user builds up an architecture in column 4 — adding Application Components, Services, and Connectors, then removing some of them — and continues clicking around the diagram. The diagram must never go blank while the underlying architecture still has content.

**Why this priority**: A diagram that silently blanks out mid-edit looks like data loss and blocks the diagram-editing workflow entirely (column 4 is a P1 area per prior iterations); a page refresh is not an acceptable workaround for a primary editing surface.

**Independent Test**: (1) Add an Application Component, add a Service to it, delete the Service, then delete the Application Component — confirm the diagram continues showing the architecture's remaining content without blanking, matching what a page refresh would show. (2) Click repeatedly through diagram elements (select, deselect, select another, resize, etc.) in varied sequences — confirm the diagram never renders as blank space while the architecture still has content.

**Acceptance Scenarios**:

1. **Given** an Architecture diagram with at least one Application Component, **When** the user adds a Service to a new Application Component, deletes that Service, and then deletes that Application Component, **Then** the diagram continues to render the architecture's remaining Collections and Connectors without going blank.
2. **Given** an Architecture diagram with several Collections, Connectors, and Services, **When** the user clicks through a variety of diagram elements in sequence (selecting, deselecting, resizing), **Then** the diagram never renders as empty space while the architecture still has content, and no page refresh is required to restore it.

---

### User Story 4 - Connectors carry exactly one Service each, and collections can have multiple connectors between them (Priority: P2)

A user should not be able to add more than one Service to a single Connector (today the UI allows adding several, but only one visibly appears — a broken, confusing state). Instead, a user who wants a second service between the same two Collections adds a second, separate Connector. Multiple Connectors between the same pair of Collections must each remain visible and clickable, not stacked directly on top of one another.

**Why this priority**: This is a data-model correction that resolves a confusing broken state (services silently failing to appear) into a coherent one; it's foundational to trusting column 4's connector/service editing, but not as urgent as the P1 correctness and stability bugs above.

**Independent Test**: Attempt to add a second Service to a Connector that already has one; confirm the second service is refused per the resolved behavior below rather than silently vanishing. Separately, create two Connectors between the same two Collections and confirm both render as distinguishable, independently clickable edges.

**Acceptance Scenarios**:

1. **Given** a Connector that already has one Service, **When** the user attempts to add a second Service to that same Connector, **Then** the system refuses the addition, the Connector still shows exactly the one Service it had, and a clear message directs the user to create a new Connector for the second service.
2. **Given** two Collections with no Connector between them, **When** the user creates two separate Connectors between the same pair of Collections (each carrying its own Service), **Then** both Connectors are visually distinguishable and independently selectable — neither fully overlaps or hides the other.

---

### User Story 5 - The service search shows how many results are on screen (Priority: P2)

While searching for a service to add in column 2's "Add a Service" section, a user needs to know whether they're looking at the complete set of matches or a truncated subset.

**Why this priority**: Users can otherwise be misled into thinking a search returned everything when results were capped, leading them to miss the service they wanted.

**Independent Test**: Run a search that returns more matches than are displayed; confirm the "n of m services displayed" text appears in red beneath the search fields. Run a search where every match is displayed; confirm the text either reads n of m with n equal to m, or is not styled as a warning (see Functional Requirements).

**Acceptance Scenarios**:

1. **Given** a service search whose total matches exceed what is currently shown, **When** the results render, **Then** text reading "n of m services displayed" appears directly below the three search fields and above the results list, with n (displayed count) and m (total match count) substituted, styled in red.
2. **Given** a service search whose total matches all fit within what is displayed (n equals m), **When** the results render, **Then** the same text is shown but is not styled as a warning (not red).

---

### User Story 6 - Pricing values are easier to read and reflect the correct data timestamp (Priority: P2)

In column 5, a user reading price totals, Price Change, and the per-SKU breakdown needs large numbers to be legible at a glance, and needs to know which pricing data snapshot a calculation used — without the current, more verbose sentence.

**Why this priority**: Pure formatting/copy correction with no behavior risk, but it affects the primary output of the tool (the price itself) and so ranks above pure visual polish.

**Independent Test**: Calculate a price with a total in the thousands or more; confirm thousand separators appear in the total, Price Change, and per-SKU breakdown values. Confirm the old "For 1 month, priced from snapshot YYYY-MM-DD" sentence is gone and a "Data Timestamp: YYYY-MM-DD" line appears at the bottom of the column with the same date.

**Acceptance Scenarios**:

1. **Given** a calculated price whose total is 1,000 or greater, **When** column 5 renders the total, Price Change, and per-SKU breakdown, **Then** each of those numeric values displays with comma thousand separators.
2. **Given** any successful calculation, **When** column 5 renders, **Then** the sentence "For {duration}, priced from snapshot {date}" no longer appears, and a line reading "Data Timestamp: {date}" appears at the bottom of the column, where {date} is the same snapshot date the calculation used.

---

### User Story 7 - The architecture diagram is easier to read and its layout survives a reload (Priority: P3)

A user styling and arranging their architecture diagram in column 4 needs less visual clutter (no redundant collection-type label), clearer boundaries (darker collection border, a border around each service), a clear indication of what's selected (underlined name), a single well-indicated way to resize a collection box, more breathing room between components, and smaller diagram text — and needs any manual sizing, spacing, and positioning they set to survive a page reload, the same way 008 already persists diagram content.

**Why this priority**: Valuable readability and persistence polish, but none of it blocks correct pricing or correct data — purely presentational, matching the P3 tier used for equivalent work in 008.

**Independent Test**: Open a diagram with a Collection, confirm no collection-type text is shown, confirm the collection border is visibly darker than before and each Service has its own border. Select an Application Component/Connector/Service and confirm its name is underlined. Resize a Collection box only from its bottom-right corner (confirm a visual resize-affordance indicator is present there, and that dragging from any other edge/corner does not resize it). Reload the page and confirm the resized size, adjusted spacing, and repositioned elements are unchanged. Confirm diagram text is noticeably smaller than the rest of the UI, and spacing between components is visibly larger than before.

**Acceptance Scenarios**:

1. **Given** a diagram with at least one Collection, **When** the user views it, **Then** no collection-type label is shown on the Collection, the Collection's border renders in a visibly darker shade than before, and each Service within a Collection shows its own border.
2. **Given** a diagram with a selected Application Component, Connector, or Service, **When** the user views the diagram, **Then** the name of the selected object is underlined and no other object's name is.
3. **Given** a Collection box, **When** the user drags from its bottom-right corner, **Then** the box resizes; **when** the user drags from any other edge or corner, **then** the box does not resize.
4. **Given** a Collection box, **When** the user views it, **Then** a visual resize-affordance indicator appears at its bottom-right corner, styled consistently with the existing whole-diagram resize indicator.
5. **Given** a user has resized a Collection box, adjusted component spacing, or repositioned elements, **When** the page is reloaded, **Then** the diagram renders with those same sizes, spacing, and positions.
6. **Given** the application's base font size, **When** text renders elsewhere in the UI versus inside the architecture diagram, **Then** diagram text is reduced by three size steps and non-diagram text is reduced by one size step, both relative to 008's sizing.

---

### User Story 8 - Adding a Connector doesn't require selecting two Collections first (Priority: P3)

A user wants to add a Connector between two Collections via an explicit "Add Connector" action, without first having to multi-select both Collections and then find the connect action. Clicking the button opens a small dialog with "From Collection" and "To Collection" dropdowns — each populated with every Application Component and VPC in the Architecture — that the user fills in and confirms.

**Why this priority**: A discoverability/ergonomics improvement to an existing capability (connecting is already possible today) — valuable but not correctness-critical.

**Independent Test**: Click "Add Connector" without pre-selecting anything, confirm a dialog appears with "From Collection" and "To Collection" dropdowns listing all Collections, pick two and confirm, and verify a Connector is created between them; the existing select-two-then-connect flow keeps working unchanged.

**Acceptance Scenarios**:

1. **Given** a diagram with at least two Collections and no pre-selection, **When** the user clicks the new "Add Connector" button, **Then** a dialog opens with "From Collection" and "To Collection" dropdowns, each populated with every Application Component and VPC in the Architecture.
2. **Given** the "Add Connector" dialog is open, **When** the user selects a Collection in each dropdown and confirms, **Then** a new Connector is created between the two chosen Collections and the dialog closes.
3. **Given** the pre-existing flow, **When** the user selects two Collections and clicks the existing connect action, **Then** a Connector is created exactly as it is today.

---

### User Story 9 - AWSDataTransfer services are identifiable by region pair (Priority: P3)

When a user works with a service whose service code is `AWSDataTransfer`, the SKU-level detail is unhelpful on its own — the meaningful information is which region the transfer is *from* and which it is *to*. A user needs to filter and recognize these services by that region pair everywhere they appear: the service search results in column 2, the diagram label in column 4, and the per-SKU price breakdown in column 5.

**Why this priority**: Narrow in scope (one service code) and does not block any other workflow — a targeted usability improvement for a specific, already-supported service family.

**Independent Test**: Search for a service with service code `AWSDataTransfer`; confirm the search results, once added, show a region-pair label instead of/alongside the raw SKU, and that the region-pair label (not the SKU) is what appears in the diagram and the price breakdown for that service. Confirm dedicated "From region" and "To region" fields appear and narrow the search.

**Acceptance Scenarios**:

1. **Given** a search result whose service code is `AWSDataTransfer`, **When** the result is displayed in column 2's service list, **Then** it shows a label in the form "{fromRegionCode}=>{toRegionCode}" derived from that SKU's region fields.
2. **Given** an `AWSDataTransfer` Service placed in the diagram, **When** the diagram renders that Service's label, **Then** it shows the same "{fromRegionCode}=>{toRegionCode}" label instead of the raw SKU.
3. **Given** a calculated price that includes an `AWSDataTransfer` Service, **When** column 5's per-SKU breakdown lists that line, **Then** it shows the same "{fromRegionCode}=>{toRegionCode}" label instead of the raw SKU.
4. **Given** the service search filter fields, **When** the user is searching for `AWSDataTransfer` services, **Then** dedicated "From region" and "To region" selector fields are available to narrow results, distinct from the three general search fields.

---

### Edge Cases

- SKU `2AB37QDFJZBGQ5YP` (US1): if investigation shows the SKU genuinely has no vendor pricing data available (as opposed to a defect in how the app looks it up), the system MUST report that as a clear "no pricing available" outcome rather than a calculation-wide failure — it must never silently break the rest of the calculation.
- Price Change duration adjustment (US2): if the user changes both the architecture's contents *and* the Duration in the same edit, the existing duration-adjusted comparison behavior (recalculating the prior selections at the new duration) continues to apply unchanged — US2 only fixes the previously-unhandled duration-only case.
- Diagram blank-screen (US3): if the *entire* architecture is emptied out (every Collection and Connector removed), an empty-but-rendered diagram (or an explicit "no content" empty state) is the correct outcome — not a bug. The bug this story fixes is a blank diagram that still has underlying content according to a refresh.
- Connector/Service limit (US4): removing a Connector's only Service leaves an empty Connector in place (it does not delete the Connector) — deleting a Connector remains a separate, explicit action, unchanged from today.
- Connector/Service limit (US4): there is no cap on how many separate Connectors may exist between the same pair of Collections; each one carries at most one Service.
- Service search count (US5): if a search returns zero matches, no "n of m" text is shown (there is nothing to compare against) — the existing empty-results state applies.
- Pricing formatting (US6): thousand separators apply to whole and fractional values alike (e.g., "1,234.56"); values under 1,000 are unaffected in appearance.
- Diagram resize (US7): the bottom-right-only resize constraint applies to Collection boxes; it does not change how individual Service or Application Component nodes are sized (if they are not independently resizable today, this story does not make them resizable).
- AWSDataTransfer (US9): a service whose code is not `AWSDataTransfer` is entirely unaffected by this story — it keeps showing its SKU/name as it does today.
- Add Connector dialog (US8): selecting the same Collection in both "From" and "To" dropdowns is rejected — the dialog cannot be confirmed in that state.
- Add Connector dialog (US8): with fewer than two Collections in the Architecture, the "Add Connector" button remains available but the dialog cannot be confirmed (fewer than two distinct choices exist).

## Requirements *(mandatory)*

### Functional Requirements

**SKU pricing failure (US1)**

- **FR-001**: The system MUST successfully calculate a price for instance SKU `2AB37QDFJZBGQ5YP` when it is included in an Architecture, unless that SKU genuinely has no vendor pricing data available, in which case the system MUST surface that as an explicit "unpriceable" result for that line (consistent with how other genuinely unpriceable SKUs are already handled) rather than failing the calculation.

**Price Change duration adjustment (US2)**

- **FR-002**: When a Prior Calculation baseline exists and the user changes only the pricing Duration (no change to the architecture's selections), the system MUST recompute the comparison total for the prior selections at the new Duration and update Price Change to reflect that duration-adjusted comparison, rather than leaving Price Change at its previous value.
- **FR-003**: The duration-only case (FR-002) MUST use the same duration-adjusted calculation path already used when content and Duration change together (i.e., recalculating the prior selections' total at the new duration via the existing snapshot-calculation capability), not a client-side numeric estimate.
- **FR-004**: Switching Duration back to the value the Prior Calculation baseline was originally established at MUST restore Price Change to the value it showed at that duration.

**Architecture diagram stability (US3)**

- **FR-005**: The architecture diagram MUST continue rendering the architecture's current Collections, Connectors, and Services after any sequence of add/delete operations on Application Components and Services, without requiring a page refresh to show correct content.
- **FR-006**: The architecture diagram MUST continue rendering correctly after repeated user interaction with diagram elements (select, deselect, resize, and similar), without entering a blank-canvas state while the underlying architecture still has content.

**Connector/Service data model (US4)**

- **FR-007**: A Connector MUST carry at most one Service at a time.
- **FR-008**: When a user attempts to add a Service to a Connector that already has one, the system MUST refuse the addition, leave the Connector's existing Service unchanged, and present a clear message directing the user to create a new Connector (FR-026) for the second service.
- **FR-009**: Users MUST be able to create more than one Connector between the same pair of Collections, each carrying its own single Service.
- **FR-010**: When multiple Connectors exist between the same pair of Collections, the diagram MUST render each as a distinguishable, independently selectable edge — no two Connectors between the same pair may fully overlap so as to hide one another.

**Service search coverage indicator (US5)**

- **FR-011**: Column 2's "Add a Service" section MUST display, directly below the three search fields and above the results list, text of the form "n of m services displayed", where n is the number of services currently shown and m is the total number of services matching the current search criteria.
- **FR-012**: This text MUST render in a red/warning style whenever n is less than m, and MUST NOT render in that warning style when n equals m.
- **FR-013**: This text MUST NOT be shown when a search returns zero total matches.

**Pricing display (US6)**

- **FR-014**: All numeric pricing values displayed in column 5 — the total price, Price Change, and each line of the per-SKU price breakdown — MUST render with comma thousand separators.
- **FR-015**: Column 5 MUST NOT display the sentence "For {duration}, priced from snapshot {date}" below the total price and Price Change.
- **FR-016**: Column 5 MUST display, at the bottom of the column, a line reading "Data Timestamp: {date}", where {date} is the same pricing-data snapshot date the removed sentence (FR-015) used to show.

**Architecture diagram styling and behavior (US7)**

- **FR-017**: A Collection's box in the diagram MUST NOT display its collection type as text.
- **FR-018**: A Collection's box border MUST render in a visibly darker shade than it does today.
- **FR-019**: Each Service shown within a Collection MUST render with its own visible border.
- **FR-020**: A Collection box MUST be resizable only by dragging its bottom-right corner; dragging any other edge or corner MUST NOT resize it.
- **FR-021**: A Collection box MUST show a visual resize-affordance indicator at its bottom-right corner, styled consistently with the diagram's existing resize-indicator visual language.
- **FR-022**: Text size throughout the application (outside the architecture diagram) MUST be reduced by one step from its 008 sizing; text size inside the architecture diagram MUST be reduced by three steps from its 008 sizing.
- **FR-023**: Spacing between components in the architecture diagram MUST be visibly increased from its 008 sizing.
- **FR-024**: When a user resizes a Collection box, adjusts diagram spacing, or repositions diagram elements, those adjustments MUST persist across a page reload, using the same per-browser, per-Architecture persistence mechanism the diagram already uses for its content (005/007/008 precedent).
- **FR-025**: The name of whichever Application Component, Connector, or Service is currently selected in the diagram MUST render underlined; no unselected object's name may render underlined.
- **FR-026**: The diagram MUST provide an explicit "Add Connector" button that opens a dialog with "From Collection" and "To Collection" dropdown fields, each populated with every Application Component and VPC in the Architecture, letting the user create a new Connector between two Collections of their choosing without first pre-selecting them on the canvas — in addition to the existing select-two-and-connect flow, which MUST continue to work unchanged.
- **FR-026a**: The "Add Connector" dialog MUST prevent confirming with the same Collection chosen in both the "From" and "To" dropdowns.

**AWSDataTransfer handling (US9)**

- **FR-027**: For any SKU whose service code is `AWSDataTransfer`, the system MUST derive a display label of the form "{fromRegionCode}=>{toRegionCode}" from that SKU's region fields.
- **FR-028**: This derived label MUST be used, in place of the raw SKU/name, everywhere that SKU is shown to the user: column 2's service search results, the diagram's label for that Service in column 4, and column 5's per-SKU price breakdown line for that Service.
- **FR-029**: Column 2's service search MUST offer the user a way to narrow `AWSDataTransfer` search results by "from" region and by "to" region, via dedicated "From region" and "To region" selector fields that appear for AWSDataTransfer-relevant searches, distinct from the three existing general search fields.
- **FR-030**: Services whose service code is not `AWSDataTransfer` MUST be entirely unaffected by FR-027–FR-029 and continue to display as they do today.

### Key Entities

- **Connector**: A directed or undirected link between two Collections in an Architecture's diagram, carrying at most one Service (corrected from today's broken "multiple accepted, only one visible" state). Multiple Connectors may exist between the same pair of Collections.
- **Collection**: A grouping node in the diagram (VPC or Application Component) whose box size, and now also whose user-adjusted spacing/position, is part of the diagram's persisted layout state.
- **Prior Calculation (baseline)**: The previously-accepted price calculation for an Architecture, now understood to be re-evaluatable at a different Duration (via the existing snapshot-calculation capability) purely because Duration changed, not only because content changed.
- **AWSDataTransfer Service**: A Service whose service code is `AWSDataTransfer`, distinguished from other services by having meaningful `fromRegionCode`/`toRegionCode` fields that this iteration surfaces as a derived display label.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: SKU `2AB37QDFJZBGQ5YP` prices successfully in 100% of calculation attempts where it is a valid selection (or is clearly reported as unpriceable, never as a hard failure).
- **SC-002**: A duration-only change (no content change) updates Price Change to the correct duration-adjusted value in 100% of cases, verified against the same value the duration-and-content-adjusted path already produces for an equivalent scenario.
- **SC-003**: Zero diagram blank-outs occur across the two documented repro sequences (component/service add-then-delete; repeated element interaction) after the fix, across repeated manual verification passes.
- **SC-004**: 100% of attempts to add a second Service to an already-occupied Connector resolve per the clarified conflict behavior, never silently dropping the addition without feedback.
- **SC-005**: A user can tell, without any explanation, whether a service search returned more matches than are displayed, purely from the "n of m" indicator's presence and color.
- **SC-006**: Every column-5 numeric value of 1,000 or more displays with thousand separators in a manual read-through of a representative calculation.
- **SC-007**: A user reloading the page after adjusting diagram sizing/spacing/position sees the identical layout they left, in 100% of manual verification passes.
- **SC-008**: A user can identify an `AWSDataTransfer` service's transfer direction (from/to region) at a glance, in the search list, the diagram, and the price breakdown, without opening any further detail.

## Assumptions

- "Column 2", "column 4", and "column 5" refer to the Architecture Editor, Architecture Diagram, and Pricing columns respectively, per 008's five-column layout and terminology; this iteration does not change that layout.
- "One size step" / "three size steps" (FR-022) means steps in the application's existing font-size scale (the same scale 008 introduced when it reduced the base font size for its sky-colored theme), applied as a further reduction on top of 008's sizing — not an absolute pixel value.
- The diagram's "existing resize indicator" (FR-021) refers to the whole-diagram resize affordance already present from prior iterations (005 precedent); this iteration reuses that same visual language at the Collection-box level rather than inventing a new indicator style.
- "Proportional to the duration change" (US2) means the ratio between the app's two supported Durations (1 month, 1 year) — there is no third duration option to account for.
- The `AWSDataTransfer` region-pair label (US9) is presentational only; it does not change which SKU is actually selected, priced, or stored — only how it is displayed.
- Persisting Collection-box size/spacing/position adjustments (FR-024) reuses the existing per-browser, per-Architecture `localStorage`-based diagram-layout persistence already established in 005/007/008, not a new Postgres-backed mechanism (Constitution Principle II: this is UI/session state, not user-defined domain data).
- Removing a Connector's only Service does not delete the Connector itself; connector deletion remains a separate, unchanged, explicit user action.
- FR-008's refusal message reuses the app's existing inline `ErrorMessage` pattern (already used consistently across every panel for validation/action errors) rather than introducing a toast/notification mechanism.
