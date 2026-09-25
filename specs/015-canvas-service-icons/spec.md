# Feature Specification: Canvas Service Icons & Per-Architecture Pricing Results

**Feature Branch**: `015-canvas-service-icons`

**Created**: 2026-09-25

**Status**: Draft

**Input**: User description: "see docs/functionality_2026-09-25_2.md" — (1) replace the per-service text in the architecture canvas (column 4) with standard AWS service icons, showing today's text (reformatted) in a hover pop-up, with icons scaling with canvas zoom; (2) fix the pricing column (column 5) so it shows the last calculated result for the *active* architecture, calculating one automatically when none exists; (3) move the Price per Sku word-wrap toggle next to the "Price per Sku" heading, right-aligned with the prices (added by the user during clarification).

## Clarifications

### Session 2026-09-25

- Q: Should each architecture's last calculated price survive a page reload / return visit? → A: Yes — saved per architecture in this browser (survives reloads on the same browser/device; not synced across devices, not stored server-side).
- Q: What should the pricing column show when the architecture changed after its saved result was calculated? → A: Show the saved result plus an "Architecture has been updated since last pricing" notice, displayed directly below the Data Timestamp line at the bottom of the column; no automatic recalculation.
- Q: Should the pop-up's description line be the group description only, or today's identifying-detail summary? → A: Today's summary (whichever of instance type, memory, vCPU, operating system, storage, group, group description are present, joined as today), on its own line.
- User addition (outside the question loop): move the Price per Sku word-wrap toggle from the very bottom of the pricing column to the right of the "Price per Sku" heading, right-aligned with the price values.
- Q: On switching architectures, should the Duration dropdown follow the saved result's duration or stay global? → A: Remembered per architecture — switching sets the dropdown to that architecture's saved-result duration; an architecture with no saved result is auto-calculated at the dropdown's current value.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See services as AWS icons on the canvas (Priority: P1)

A user building an architecture looks at the canvas and, instead of a stack of text rows such as `AmazonDynamoDB / 3ERQSZWPAMX2JWHN -- DynamoDB PayPerRequest Read Request Units`, sees the standard AWS architecture icon for each service placed inside its Application Component or VPC box. The diagram reads like a conventional AWS architecture diagram at a glance. The same service added several times (e.g. three DynamoDB SKUs) shows the same icon several times.

**Why this priority**: This is the headline change — it makes the canvas legible as an architecture diagram and removes the text clutter that dominates boxes today.

**Independent Test**: Open an architecture containing services from several AWS services (e.g. EC2, S3, DynamoDB, Lambda, data transfer) and confirm each service appears as a recognizable AWS icon (or the generic fallback icon), with no service text rows on the canvas.

**Acceptance Scenarios**:

1. **Given** an Application Component containing an AmazonDynamoDB SKU, **When** the canvas renders, **Then** the component box shows the official DynamoDB icon in place of the text row.
2. **Given** a box containing two different SKUs of the same service, **When** the canvas renders, **Then** the same icon appears twice, one per SKU.
3. **Given** a service whose service code / product family matches no available icon, **When** the canvas renders, **Then** a generic AWS fallback icon is shown (never a blank or broken image).
4. **Given** an icon on the canvas, **When** the user clicks it, **Then** that service becomes the selected service exactly as clicking the text row does today (selected-state indication preserved).
5. **Given** boxes, VPCs, and connectors on the canvas, **When** the canvas renders, **Then** box names, VPC names, connector labels, and the "No services yet." message are unchanged (only per-service rows become icons).

---

### User Story 2 - Hover an icon to see the service details (Priority: P1)

A user hovers over (or keyboard-focuses) an icon to see which exact SKU it represents. A pop-up shows the details on separate labeled lines instead of the old single slash/dash-joined line.

**Why this priority**: Without the pop-up, switching to icons would lose information users rely on today; this story must ship together with Story 1.

**Independent Test**: Hover each icon on a sample architecture and compare the pop-up content against the SKU's details.

**Acceptance Scenarios**:

1. **Given** an icon for AmazonDynamoDB SKU 3ERQSZWPAMX2JWHN with group description "DynamoDB PayPerRequest Read Request Units", usage type "EU-ReadRequestUnits", and operation "PayPerRequestThroughput", **When** the user hovers it, **Then** the pop-up shows, each on its own line:
   ```
   AmazonDynamoDB
   Sku: 3ERQSZWPAMX2JWHN
   DynamoDB PayPerRequest Read Request Units
   UsageType: EU-ReadRequestUnits
   Operation: PayPerRequestThroughput
   ```
2. **Given** a SKU lacking a group description, usage type, and/or operation, **When** the user hovers its icon, **Then** each missing line is omitted entirely (no empty label such as "UsageType:" with no value).
3. **Given** the pointer leaves the icon, **When** it moves away, **Then** the pop-up disappears.
4. **Given** a keyboard user tabs to an icon, **When** it receives focus, **Then** the same pop-up content is shown, and the icon's accessible name conveys the same details.

---

### User Story 3 - Icons and pop-ups scale with canvas zoom (Priority: P2)

A user zooms the canvas out to see a large architecture or in to inspect a region. Icons (and their pop-ups) grow and shrink with the zoom level just as the canvas text does today.

**Why this priority**: Important for usability on large diagrams, but the canvas is still usable at the default zoom without it.

**Independent Test**: Use the zoom in / zoom out controls and confirm icon size changes proportionally to box and label size, and pop-up size follows.

**Acceptance Scenarios**:

1. **Given** the canvas at 100% zoom, **When** the user clicks zoom-in, **Then** icons render larger in the same proportion as box labels.
2. **Given** the canvas zoomed out, **When** the user hovers an icon, **Then** the pop-up is scaled consistently with the zoomed canvas (as canvas text is today).
3. **Given** the pop-out (enlarged) canvas view, **When** it renders, **Then** icons and pop-ups behave identically to the in-column canvas.

---

### User Story 4 - Pricing column shows the active architecture's own result (Priority: P1)

A user calculates the price for Architecture A, switches to Architecture B, and later returns to A. Today the pricing column keeps showing whichever calculation was run last, even if it belonged to a different architecture. After this change, the pricing column always shows the last calculated result (total, per-SKU breakdown, warnings, unpriceable notices, and price change) belonging to the architecture currently selected. If the selected architecture has no stored result in this browser, it is calculated automatically and the result populated.

**Why this priority**: This is a correctness defect — showing one architecture's price while another is active is misleading in a pricing tool.

**Independent Test**: Calculate A, switch to B (never calculated), observe B is calculated automatically; switch back to A and observe A's earlier result (not B's) with no new calculation.

**Acceptance Scenarios**:

1. **Given** A was calculated and B was never calculated, **When** the user switches to B, **Then** B is calculated automatically and B's result is displayed.
2. **Given** both A and B have been calculated, **When** the user switches from B back to A, **Then** A's last result (total and breakdown) is displayed immediately without recalculating.
3. **Given** A is active, **When** the user clicks Calculate, **Then** only A's stored result is replaced; B's stored result is unaffected.
4. **Given** a stored result for A computed at 1 month and the Duration dropdown currently set to 1 year (while B is active), **When** A becomes active, **Then** the Duration dropdown changes to 1 month, matching A's displayed result.
4a. **Given** the Duration dropdown is set to 1 year and C has no stored result, **When** C becomes active, **Then** C is auto-calculated at 1 year and the dropdown stays at 1 year.
5. **Given** an architecture with no services, **When** it becomes active, **Then** no automatic calculation runs and the pricing column shows its normal empty state.
6. **Given** an automatic calculation fails, **When** the error is shown, **Then** it is shown for that architecture only, with the existing retry control.

---

---

### User Story 5 - Word-wrap toggle sits next to the Price per Sku heading (Priority: P3)

A user reading the per-SKU breakdown wants to toggle word wrap without scrolling to the very bottom of the pricing column. The word-wrap toggle moves from below the Data Timestamp line to the same row as the "Price per Sku" heading, at the right edge, right-aligned with the price values in the list below it.

**Why this priority**: Small layout improvement; the toggle already works, it is just hard to find.

**Independent Test**: Calculate any architecture and confirm the word-wrap toggle is on the "Price per Sku" heading row, its right edge aligned with the right edge of the price column, and that nothing remains at the bottom of the column except the Data Timestamp (and, when applicable, the out-of-date notice).

**Acceptance Scenarios**:

1. **Given** a calculated result, **When** the pricing column renders, **Then** the word-wrap toggle appears on the "Price per Sku" heading row, right-aligned with the per-SKU prices, and no longer appears at the bottom of the column.
2. **Given** the toggle in its new position, **When** the user clicks it, **Then** word wrap for the Price per Sku list turns on/off exactly as today (same pressed state and tooltip).
3. **Given** the pricing column is narrowed, **When** it renders, **Then** the toggle stays on the heading row, right-aligned, and does not overlap the heading text.

### Edge Cases

- A service appears whose service code has no close icon match: generic fallback icon is shown; the pop-up still shows full details so the service is identifiable.
- Service code matches ambiguously (e.g. several icons share a keyword): a deterministic, reviewed mapping decides — the same service always shows the same icon.
- Data-transfer services (which today show a derived region-pair label instead of the SKU): the pop-up still shows `Sku:` with the real SKU and adds the derived region-pair label as its own line.
- A box with many services: icons wrap within the box rather than overflowing it; box resizing behavior is unchanged.
- Rapid architecture switching while an automatic calculation is in flight: a late-arriving result is stored against the architecture it was requested for and never displayed under a different active architecture.
- The architecture is edited (services added/removed, or a service's pricing inputs changed) after its result was stored: the stored result is still shown, with the "Architecture has been updated since last pricing" notice below the Data Timestamp line, until the user clicks Calculate; auto-calculation only happens when no stored result exists.
- The architecture is edited and then changed back to exactly what was priced: the notice disappears, since the priced contents match again.
- The user changes Duration while viewing a stored result but does not click Calculate: behaves as today (the change takes effect on the next Calculate); if the user switches away and back before calculating, the dropdown returns to the stored result's duration.
- An architecture is deleted: its stored result is discarded.
- Page reload: stored results are retained in this browser, so an architecture calculated before the reload shows its result immediately afterward without recalculating.
- A different browser/device (or cleared browser data): no stored result exists there, so each architecture is auto-calculated the first time it becomes active.
- Browser storage unavailable or corrupted: the stored result is treated as absent (auto-calculation runs) and the app continues to work without error.

## Requirements *(mandatory)*

### Functional Requirements

**Canvas icons**

- **FR-001**: The architecture canvas MUST represent each service (SKU selection) inside an Application Component or VPC box with an AWS architecture service icon instead of a text row.
- **FR-002**: The icon for a service MUST be chosen from the official AWS Architecture Service Icons set (the package's 48-size SVG variant), based on the service's service code and, where the service code alone is insufficient, its product family.
- **FR-003**: The service-to-icon mapping MUST be derived by approximate matching between the service codes present in the pricing data and the icon file names, and the resulting mapping MUST be deterministic and reviewable (the same service code/product family always yields the same icon).
- **FR-004**: When no icon matches a service, the canvas MUST show a single, consistent generic fallback icon.
- **FR-005**: The same icon MAY appear multiple times in a diagram (one per service entry).
- **FR-006**: Clicking or activating an icon MUST select that service exactly as clicking its text row does today, with a visible selected state on the icon.
- **FR-007**: Box names, VPC names, connector labels, and empty-box messages MUST remain as they are today.

**Hover pop-up**

- **FR-008**: Hovering or keyboard-focusing an icon MUST show a pop-up containing, each on its own line and in this order: the service code; `Sku: <sku>`; the SKU's identifying-detail summary — the same summary shown on the canvas today (whichever of instance type, memory, vCPU, operating system, storage, group, and group description are present, joined as today; for many SKUs this is just the group description); `UsageType: <usage type>`; `Operation: <operation>`.
- **FR-009**: Any line whose value is unavailable MUST be omitted rather than shown empty.
- **FR-010**: For data-transfer services, the pop-up MUST include the derived region-pair label (currently shown on the canvas) as an additional line, while `Sku:` shows the real SKU.
- **FR-011**: The pop-up MUST disappear when the pointer leaves or focus moves away from the icon.
- **FR-012**: Each icon MUST expose an accessible name equivalent to its pop-up content.

**Zoom**

- **FR-013**: Icons MUST scale proportionally with the canvas zoom level, using the same zoom controls and behavior that scale canvas text today, in both the in-column and pop-out canvas views.
- **FR-014**: The pop-up MUST scale consistently with the canvas zoom level.

**Per-architecture pricing results**

- **FR-015**: The pricing column MUST keep the most recent calculation result (total, per-SKU breakdown, warnings, unpriceable notices, price change, the duration it was computed at, and a record of the priced contents used for staleness comparison) separately for each architecture, saved in the user's browser so it survives page reloads on that browser. Stored results MUST NOT be written to the application database.
- **FR-016**: The pricing column MUST display only the stored result of the currently active architecture; it MUST never display a result belonging to a different architecture.
- **FR-017**: When an architecture with at least one service becomes active and has no stored result, the system MUST calculate it automatically at the currently selected duration and display the result.
- **FR-018**: When an architecture with a stored result becomes active, the system MUST display that result immediately without recalculating.
- **FR-018a**: When the active architecture's priced contents (its services, their pricing inputs, and each service's region) differ from those used for its displayed stored result, the pricing column MUST show the notice "Architecture has been updated since last pricing" directly below the Data Timestamp line at the bottom of the column. The notice MUST disappear once the architecture is recalculated or its contents again match the priced contents. It MUST NOT trigger an automatic recalculation.
- **FR-018b**: When an architecture with a stored result becomes active, the Duration dropdown MUST be set to the duration that stored result was computed at. When an architecture with no stored result becomes active, the dropdown MUST keep its current value and the automatic calculation (FR-017) MUST use it.
- **FR-019**: Clicking Calculate MUST replace only the active architecture's stored result.
- **FR-020**: A calculation result MUST be stored against the architecture it was requested for, even if the user has switched architectures before it completes.
- **FR-021**: Calculation errors MUST be tracked per architecture and shown only while that architecture is active.
- **FR-022**: The existing price-change comparison (baseline vs. new calculation) MUST continue to work per architecture; automatic calculations MUST follow the same baseline rules as a user-initiated Calculate.

**Pricing column layout**

- **FR-023**: The Price per Sku word-wrap toggle MUST be placed on the same row as the "Price per Sku" heading, right-aligned so its right edge lines up with the per-SKU price values, and MUST no longer appear at the bottom of the pricing column. Its behavior (on/off, pressed state, tooltip, accessible name) MUST be unchanged.

### Key Entities

- **Service Icon Mapping**: Associates a service code (optionally qualified by product family) with one icon from the AWS icon set; includes a fallback entry for unmatched services.
- **Service Pop-up Content**: The ordered, labeled detail lines for one service on the canvas (service code, SKU, identifying-detail summary, usage type, operation, and for data transfer the region-pair label).
- **Architecture Pricing Result**: The last calculation result for one architecture — total, line-item breakdown, warnings, unpriceable notices, price change, duration, the priced contents (services and inputs) it was computed from, and any error — keyed by architecture.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of services on the canvas render as an icon (a matched AWS icon or the fallback); no service text rows remain on the canvas.
- **SC-002**: At least 90% of the distinct service codes in the current pricing snapshot, and every service code used in the seeded standard architectures, resolve to a matched, non-fallback icon.
- **SC-003**: For every service, hovering its icon shows a pop-up whose lines exactly match the service's available details, in the specified order, with no empty labeled lines.
- **SC-004**: Across the full range of zoom levels, icon size stays proportional to box label size (no icon remains fixed-size while text scales).
- **SC-005**: In 100% of architecture switches, the pricing column shows either the active architecture's own last result, an in-progress calculation for it, or its empty/error state — never another architecture's result.
- **SC-005a**: In 100% of cases where an architecture's services, pricing inputs, or service regions changed after its displayed result was calculated, the "Architecture has been updated since last pricing" notice is visible; it is never shown when the contents match the priced contents.
- **SC-005b**: The word-wrap toggle is reachable without scrolling past the Price per Sku list — it is on the heading row in 100% of calculated results, at every pricing column width.
- **SC-006**: Returning to a previously calculated architecture shows its result in under 1 second, with no new calculation triggered.

## Assumptions

- Only the per-service rows inside boxes become icons; box/VPC/connector presentation is otherwise unchanged.
- The needed icons (48px service icons) are copied into the application and served with it; the external icon folder is a build-time source only, not a runtime dependency. Resource/group/category icon sets are otherwise out of scope, with two exceptions from the same official package: the generic fallback uses the AWS Cloud group icon, and data-transfer services (which have no service icon) use the General "Data Stream" resource icon.
- The pop-up's description line reuses the identifying-detail summary shown on the canvas today (so EC2 still shows instance type etc.), now on its own line. UsageType and Operation come from the SKU's existing usage type and operation attributes.
- Pricing results are saved per architecture in the user's browser (the same way the existing per-architecture price-change baseline and canvas zoom are saved today), not server-side; they are not shared across browsers/devices. The existing price-change baseline continues to persist as it does today.
- A stored result is not automatically recalculated when the architecture is edited; it is flagged as out of date (FR-018a) and the user clicks Calculate to refresh. A Duration change alone does not trigger the notice (Duration is shown with the result).
- Architectures imported (copied) from another user behave like any other owned architecture.
- AWS is the only provider in scope. The icon mapping lives in an AWS-specific module keyed by AWS service code (and product family); another provider would add a sibling mapping module rather than restructure this one.
