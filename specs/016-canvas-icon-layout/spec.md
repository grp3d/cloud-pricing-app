# Feature Specification: Canvas Icon Layout, Active Pricing Snapshot & Configurable Settings

**Feature Branch**: `016-canvas-icon-layout`

**Created**: 2026-09-26

**Status**: Draft

**Input**: User description: "docs/functionality_2026-09-26.md" — (1) larger, spaced-out, draggable, non-overlapping service icons with a richer hover pop-up (more attributes, no Operation line); (2) fix error messages that appear in both column 1 and column 2; (3) place new top-level collections within the visible canvas; (4) a background check that detects new or updated pricing data and reports services with no icon to admins in an Issues table on the Admin tab; (5) move hard-coded values into settings that can be overridden by environment variables. Added during clarification: (6) a single background pricing-data service that maintains the "active snapshot date" every pricing lookup uses, switching only to fully written snapshots, and a reorganized Admin tab (User Management; System Information with the Issues table).

## Clarifications

### Session 2026-09-26

- Q: Icon spacing — "at least 2x away" from the nearest icon: 2× of what? → A: A gap of 1.5 icon widths (90px in canvas units at the new 60px icon size).
- Q: Which services does the Issues table list? → A: Every service in the latest pricing data with no icon (including today's fallback services), with a "New" marker on those first seen in the latest snapshot.
- Q: How should pricing lookups avoid reading a half-written snapshot? → A: A background service maintains one "active snapshot date" that every pricing lookup must use. It switches to a newer date only when every pricing table has that date and the upstream job's completion marker (`_SUCCESS`) is present for it in every table. The upstream job will write that marker.
- Q: What if a new complete snapshot covers fewer regions than the current one? → A: Still switch to it, and add a line to the Admin Issues table naming the missing regions.
- Q: Separate schedules for the snapshot check and the icon check? → A: No — one service does both; the icon check runs whenever the active date changes or its data is updated.
- Q: Persist the active date across restarts? → A: No — on startup it is determined afresh by the same completeness rule (the completion marker makes this safe).
- Q: Manual override? → A: Yes — a setting (overridable by environment variable) that pins the active snapshot date, e.g. to roll back from bad upstream data.
- Q: Admin tab layout? → A: The existing content becomes a "User Management" section. Below it, a "System Information" section shows the active snapshot date, when the last check ran, and any snapshot waiting to become active (and why). Under System Information, the Issues table lists non-blocking problems (services with no icon, missing regions).
- Q: Show a "newer pricing data is available" notice on stored results older than the active snapshot? → A: No — which pricing data is active is not the user's choice, so the pricing column does not flag it; the Data Timestamp line continues to show which snapshot a result used.
- Q: When icons don't fit side by side at the new spacing, should boxes widen by default or stack icons in one column? → A: The default box width grows to fit up to 3 icons per row (about 400px, later 320px when the gap became 60px); rows wrap after that. Boxes with fewer services are only as wide as needed (never narrower than today's defaults).
- Q: Where can icons be dragged — within their own box only, or into other boxes? → A: Into any other box in the same region (VPC or Application, nested or not); dropping moves the service to that box. Inside a VPC, the VPC's own icons stay in its own-services area above its nested boxes (that area grows to fit), unless dropped into one of the nested boxes. The same spacing rules apply in every box.
- Q: Can the manual override pin a snapshot date that has no completion markers? → A: Yes — any date present in every pricing table can be pinned; if it lacks markers, the server still starts and the Issues table shows a warning. A date missing from any table still prevents startup.
- Q: After a restart, what should the missing-regions check compare the active snapshot against? → A: Nothing — the check runs only when the active date switches while the server is running, against the date that was active before; it is skipped after a restart. (A persisted state table is planned for a future feature.)

- Q (after implementation review): The 90px gaps spread boxes out too much — reduce the default spacing, or keep it and let users drag icons closer? → A: Reduce it: a 60px gap (one icon width) is both the default spacing and the minimum when dragging. This supersedes the 1.5-icon-width answer above.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Larger, well-spaced service icons (Priority: P1)

A user looking at the architecture canvas finds today's icons too small and packed together. Icons are now 2.5× their current size and laid out inside each VPC or Application box with generous space between them, so each service is easy to see and pick out.

**Why this priority**: Legibility of the canvas is the most visible part of this request and affects every user on every architecture.

**Independent Test**: Open any seeded architecture; measure an icon (2.5× today's size at the same zoom) and the gap to its nearest neighbor on every side (meets the minimum spacing rule); confirm every box has grown to contain all its icons without overlap or clipping.

**Acceptance Scenarios**:

1. **Given** a box containing services, **When** the canvas renders at a given zoom, **Then** each icon is 2.5× the size it was before this change at that same zoom.
2. **Given** a box containing several services, **When** the canvas renders with default placement, **Then** every icon is separated from its nearest neighbor on all sides by at least the minimum spacing: a gap of one icon width (60px in canvas units at the new 60px icon size).
3. **Given** a box with more icons than fit on one row, **When** the canvas renders, **Then** the box grows to contain every icon with the required spacing, and nothing overlaps the box's name or region label.
4. **Given** the icons at their new size, **When** the user zooms in or out, **Then** icons and spacing scale with the canvas as they do today.

---

### User Story 2 - Drag icons to arrange a box (Priority: P2)

A user wants to arrange the services inside a box to tell a story (e.g. put the load balancer above the app servers). They drag an icon to a new spot within the same box and it stays there. They can also drag an icon into another box in the same region — for example from a VPC down into one of its Application boxes — which moves the service there. An icon can never be dropped on top of another icon.

**Why this priority**: Valuable for presenting architectures, but the canvas is usable without it once icons are larger and spaced (Story 1).

**Independent Test**: Drag an icon within its box and release; it stays where dropped (subject to spacing), survives a page reload, and never ends up covering another icon or outside its box.

**Acceptance Scenarios**:

1. **Given** an icon in a box, **When** the user drags it to an empty spot inside the same box, **Then** it stays at that spot after release and after a page reload.
2. **Given** an icon being dragged, **When** the user releases it where it would overlap another icon (or come closer than the minimum spacing), **Then** it does not cover the other icon — it is placed at the nearest valid spot instead.
3. **Given** an icon being dragged, **When** the user releases it inside another box in the same region (including a nested Application inside its VPC, or the VPC containing its Application), **Then** the service moves to that box — saved, shown under that box in column 2, and priced as part of it — and the icon is placed at the drop point (or the nearest spot that satisfies the spacing rule).
3a. **Given** an icon being dragged, **When** the user releases it over a box in a different region, or over empty canvas outside any box, **Then** the service does not move and the icon returns to its previous position; a cross-region drop shows an explanation in column 2.
3b. **Given** a VPC that contains nested Application boxes, **When** the user drags one of the VPC's own icons within the VPC but not into a nested box, **Then** the icon stays in the VPC's own-services area above the nested boxes, and that area grows (pushing the nested boxes down) if needed.
4. **Given** an icon, **When** the user clicks it without moving it, **Then** it selects the service exactly as today (a click is not treated as a drag).
5. **Given** a box whose icons were arranged by hand, **When** a new service is added to it, **Then** the new icon is placed in the first free spot that respects the spacing rule, without moving the hand-placed icons.
6. **Given** a dragged icon, **When** it is released near the box's bottom edge, **Then** the box grows downward so the icon is never clipped; **When** it is released past the box's right edge, **Then** it is kept within the box's width (boxes widen only per FR-002's up-to-3-per-row rule, or by a manual resize).

---

### User Story 3 - Richer hover pop-up (Priority: P2)

When hovering an icon, the user also sees technical details that matter for comparing SKUs — database engine, processor, tenancy, storage type, and so on — each on its own labeled line. The Operation line, which users found unhelpful, is gone.

**Why this priority**: Improves the usefulness of the existing pop-up; small and independent.

**Independent Test**: Hover icons for an RDS, EC2, ElastiCache and EBS SKU; each shows the listed attributes that SKU has, one per line, and none shows an Operation line.

**Acceptance Scenarios**:

1. **Given** an RDS SKU with a database engine, **When** the user hovers its icon, **Then** the pop-up includes a `databaseEngine: <value>` line.
2. **Given** any SKU, **When** the user hovers its icon, **Then** the pop-up contains no `Operation:` line.
3. **Given** a SKU missing some of the listed attributes, **When** the user hovers its icon, **Then** only the attributes it actually has are shown — no empty lines.
4. **Given** an attribute that already appears in the pop-up's summary line (e.g. memory), **When** the pop-up is shown, **Then** that value is shown once, on its own labeled line, not twice.

---

### User Story 4 - Pricing always uses one complete snapshot (Priority: P1)

The upstream job writes new pricing data into dated folders. Today every lookup picks the newest date on its own, so it can read a snapshot the job is still writing. A background service now maintains a single "active snapshot date", and every pricing lookup — search, calculation, attribute and unit lookups — uses it. The service moves to a newer date only once the upstream job has marked that date complete in every pricing table.

**Why this priority**: It protects the correctness of every price shown (Constitution Principle I); a half-written snapshot can silently produce wrong or missing prices.

**Independent Test**: Start writing a new snapshot without its completion markers; lookups keep using the previous date. Add the markers to every table; within one check interval, lookups switch to the new date and the Admin tab shows it as active.

**Acceptance Scenarios**:

1. **Given** a newer snapshot date that exists in every pricing table with a completion marker in each, **When** the next check runs, **Then** it becomes the active snapshot date and all subsequent pricing lookups use it.
2. **Given** a newer snapshot date that is missing from any table, or missing the completion marker in any table, **When** a check runs, **Then** the active date does not change, and the Admin tab shows the newer date as waiting, with the reason.
3. **Given** a newly complete snapshot that is missing one or more regions the current active snapshot has, **When** a check runs, **Then** it still becomes active, and the Issues table gets a line naming the missing regions.
4. **Given** the server starts, **When** it comes up, **Then** it determines the active date with the same completeness rule before serving pricing requests.
5. **Given** the manual override setting names a snapshot date, **When** the server runs, **Then** that date is the active date regardless of newer complete data, and the Admin tab shows that it is pinned.
6. **Given** a request that started before the active date changed, **When** it finishes, **Then** it used one snapshot date throughout (never a mix of two).
7. **Given** the check interval is set in configuration, **When** the server runs, **Then** checks happen at that interval (default every 5 minutes).

---

### User Story 5 - Admins see system status and problems (Priority: P2)

An admin opens the Admin tab and sees, beyond user management, how the pricing data is doing: which snapshot is active, when it was last checked, whether a newer one is waiting, and a list of non-blocking problems — services that have no icon and regions missing from the active snapshot.

**Why this priority**: Makes the new background service observable and keeps icon coverage from silently degrading as AWS adds services; admin-only.

**Independent Test**: As an admin, open the Admin tab: it has a User Management section (today's content) and a System Information section with the active snapshot date, last check time, any waiting snapshot, and the Issues table. Add a snapshot containing a service with no icon; once it becomes active, the service is listed and marked New.

**Acceptance Scenarios**:

1. **Given** an admin opens the Admin tab, **When** it renders, **Then** today's user-management content appears under a "User Management" heading, followed by a "System Information" section.
2. **Given** the System Information section, **When** it renders, **Then** it shows the active snapshot date (and whether it is pinned by the override), when the last check ran, and any newer snapshot waiting to become active with the reason it is waiting.
3. **Given** the active snapshot contains services with no icon, **When** the Issues table renders, **Then** it lists every such service with its code, name, and the snapshot date, and marks as "New" those that first appeared in the active snapshot.
4. **Given** the active date switched while the server was running to a snapshot missing regions the previously active one had, **When** the Issues table renders, **Then** it includes a line naming them.
5. **Given** the active date changes, or its data is updated in place (its completion marker is rewritten), **When** the next check runs, **Then** the icon analysis is re-run; otherwise it is skipped.
6. **Given** a service that now has an icon (the mapping was updated and deployed), **When** the analysis next runs, **Then** it is no longer listed.
7. **Given** a non-admin user, **When** they use the app, **Then** they cannot see the System Information section or the Issues table.

---

### User Story 6 - Errors appear only in the column they belong to (Priority: P1)

A user nesting an Application into a VPC in another region correctly gets an error — but today it appears in both column 1 (architectures) and column 2 (collections). Each error now appears only in the column where the action happened.

**Why this priority**: A confirmed defect (errors from both columns share one message area); cheap to fix and confusing today.

**Independent Test**: Trigger a collection-level error (cross-region nesting) and an architecture-level error (e.g. a failed create); each appears only in its own column.

**Acceptance Scenarios**:

1. **Given** a cross-region nesting attempt, **When** the error is shown, **Then** it appears in column 2 only.
2. **Given** an architecture-level action fails (create, delete, import, share), **When** the error is shown, **Then** it appears in column 1 only.
3. **Given** an error showing in one column, **When** the user dismisses it, **Then** only that column's error clears.

---

### User Story 7 - New collections appear where the user can see them (Priority: P1)

A user adds a new top-level collection, but it sometimes lands outside the visible part of the canvas, so it looks like nothing happened. New top-level collections are now placed inside the part of the canvas the user is currently looking at, without covering existing boxes when there's room.

**Why this priority**: A confirmed defect that makes adding collections feel broken.

**Independent Test**: Pan/zoom the canvas to any area, add a top-level collection; it appears within the visible area, not overlapping existing boxes where free space exists.

**Acceptance Scenarios**:

1. **Given** the canvas is panned or zoomed to any view, **When** the user adds a top-level collection, **Then** the new box appears entirely within the visible canvas area whenever it fits.
2. **Given** free space exists in the visible area, **When** the new box is placed, **Then** it does not overlap any existing box.
3. **Given** no free spot exists in the visible area, **When** the new box is placed, **Then** it is placed in view anyway (overlap allowed) rather than off-screen.
4. **Given** a collection nested inside a VPC, **When** it is added, **Then** its placement follows today's nesting rules (unchanged).

---

### User Story 8 - Operational settings are configurable (Priority: P3)

An operator deploying the app needs to change values like the pricing data location, allowed browser origins, or the pricing-snapshot check interval without editing code. Every such value is a named setting with a sensible default that can be overridden by an environment variable.

**Why this priority**: Enables deployment beyond the developer's machine; no end-user-visible change.

**Independent Test**: Review the backend for fixed operational values; each is a named setting with a documented default; setting its environment variable changes behavior on restart.

**Acceptance Scenarios**:

1. **Given** an operational value previously fixed in code (e.g. the allowed browser origin, the default pricing region, the pricing-snapshot check interval), **When** its environment variable is set, **Then** the server uses the new value after restart.
2. **Given** no environment variable is set, **When** the server starts, **Then** it behaves exactly as it does today.
3. **Given** the full list of settings, **When** an operator looks for it, **Then** every setting, its default, and its environment variable name are documented in one place.

---

### Edge Cases

- A box has so many services that the spacing rule makes it very large: the box grows in height (3 icons per row); the canvas remains scrollable/zoomable.
- A user manually resizes a box narrower than its icons' row needs: the box can't be made narrower than one icon plus its padding, and icons in default placement re-flow to fewer per row; hand-placed icons that would fall outside move to the nearest valid spot.
- An icon's saved position is no longer valid (e.g. the box was manually resized smaller, or a service was removed): icons are re-placed at the nearest valid spot; nothing overlaps or is clipped.
- A service is deleted from a box with hand-placed icons: the remaining icons keep their positions.
- Moving a service to another box fails on the server (e.g. a network error): the icon returns to its original box and position, and the error shows in column 2.
- A service is moved into a box that already has hand-placed icons: existing icons keep their positions; the moved icon takes the drop point or the nearest valid spot.
- Dragging while the canvas is zoomed: drag distance follows the pointer at any zoom.
- The pricing data directory is unreadable when a check runs: the active date stays as it is, the problem is logged and shown on the Admin tab, and the check tries again at the next interval.
- Two checks overlap (a slow check still running when the next is due): the second is skipped.
- No complete snapshot exists at startup (and no override): pricing lookups report pricing data as unavailable, as they do today when no usable snapshot exists, and the Admin tab shows why.
- The override names a date that is missing from any pricing table: the server refuses to start, with a message naming the setting. If the date exists in every table but lacks completion markers, the server starts and shows a warning in the Issues table.
- A newer complete snapshot appears while an older one is still waiting: the newest complete one becomes active.
- The server restarts: the active date and the icon issues are recomputed at startup from the data on disk (nothing is persisted); a missing-regions issue recorded before the restart is not re-reported.
- An environment variable holds an invalid value (e.g. a non-numeric interval): the server refuses to start with a clear message naming the setting.

## Requirements *(mandatory)*

### Functional Requirements

**Canvas icons**

- **FR-001**: Service icons on the canvas MUST be 2.5× their current size at any given zoom level.
- **FR-002**: By default, icons within a box MUST be placed so each is at least one icon width (60px in canvas units) from its nearest neighbor on all sides, in the box's service order, up to 3 icons per row, wrapping after that. The same 60px is the closest a drag may place two icons. A box's default width MUST be just wide enough for its widest row (at most 3 icons, 320px), and never narrower than today's defaults.
- **FR-003**: A box MUST always be large enough to contain all its icons at their positions plus spacing, without overlapping the box's name or region label.
- **FR-004**: Users MUST be able to drag an icon to a new position within its own box. Within a VPC, the VPC's own icons MUST stay in its own-services area above its nested boxes, which grows to fit them.
- **FR-004a**: Dropping an icon inside another box in the same region (VPC or Application, nested or not) MUST move that service to that box, persisted like any other change to the architecture, with the icon placed at the drop point or the nearest spot satisfying the spacing rule.
- **FR-004b**: Dropping an icon over a box in a different region, or outside every box, MUST leave the service where it was and return the icon to its previous position; a cross-region drop MUST show an explanation in column 2.
- **FR-005**: A dropped icon MUST NOT overlap another icon; if the drop position would violate the spacing rule, the icon MUST be placed at the nearest valid position.
- **FR-006**: Hand-placed icon positions MUST persist across page reloads, in the same way box positions and sizes persist today.
- **FR-007**: A click on an icon without movement MUST continue to select the service; drag MUST NOT trigger selection changes beyond what a click does.
- **FR-008**: New icons added to a box MUST be placed at the first free position that satisfies the spacing rule, without moving existing icons.

**Hover pop-up**

- **FR-009**: The pop-up MUST include each of these attributes, when present on the SKU, as its own `<attribute>: <value>` line, in this order: databaseEngine, processorArchitecture, physicalProcessor, clockSpeed, tenancy, storageType, cacheEngine, networkPerformance, memory, storageMedia, volumeType, minVolumeSize, maxVolumeSize, storageClass, deploymentOption.
- **FR-010**: The pop-up MUST NOT show an Operation line.
- **FR-011**: A value shown on its own labeled line MUST NOT be repeated in the pop-up's summary line.

**Error placement**

- **FR-012**: Errors from architecture-level actions MUST appear only in column 1; errors from collection-, connector-, and nesting-level actions MUST appear only in column 2. Dismissing an error MUST clear it only in its own column.

**New collection placement**

- **FR-013**: A new top-level collection MUST be placed entirely within the canvas area currently visible to the user whenever it fits, and MUST NOT overlap an existing box when a free spot exists in the visible area.

**Active pricing snapshot**

- **FR-014**: The server MUST maintain a single active snapshot date, and every pricing-data lookup MUST use it; no lookup may choose a snapshot date on its own.
- **FR-015**: A background check MUST run periodically (default every 5 minutes, configurable) and make a newer snapshot date active only when every pricing table contains that date and each has the upstream completion marker for it.
- **FR-016**: When the active date switches while the server is running and the new snapshot lacks regions present in the previously active one, the switch MUST still happen and an issue naming the missing regions MUST be recorded. The check is not performed at startup (there is no previously active date then).
- **FR-017**: At startup the active date MUST be determined by the same rule before pricing requests are served; it is not persisted between runs.
- **FR-018**: A setting MUST allow pinning the active date to a specific snapshot; when set, the background check MUST NOT change it. Any date present in every pricing table MUST be accepted; if it lacks a completion marker in any table, the server MUST still start and the Issues table MUST show a warning saying so. A date missing from any table MUST prevent startup, with a message naming the setting.
- **FR-019**: A single request MUST use one snapshot date throughout, even if the active date changes while it is in progress.

**System information & issues (Admin tab)**

- **FR-020**: The Admin tab MUST present today's content under a "User Management" section, followed by a "System Information" section, visible only to admins.
- **FR-021**: System Information MUST show the active snapshot date (and whether it is pinned), the time of the last check, and any newer snapshot waiting to become active with the reason it is waiting.
- **FR-022**: Under System Information, an Issues table MUST list non-blocking problems: (a) each service in the active snapshot that cannot be linked to an icon — with service code, service name, snapshot date, and a "New" marker if it first appeared in the active snapshot; (b) regions missing from the active snapshot relative to the previously active one (FR-016); (c) a pinned snapshot that lacks completion markers.
- **FR-023**: The icon analysis MUST run when the active date changes or the active snapshot's data is updated in place (its completion marker changes), and at startup; otherwise it MUST be skipped. The icon analysis MUST use the same icon mapping the canvas uses.
- **FR-024**: A service that can now be linked to an icon MUST no longer be listed after the next analysis.

**Configuration**

- **FR-025**: Every operational value currently fixed in the backend code (including but not limited to: allowed browser origins, default pricing region, pricing data location, the snapshot check interval, the active-date override) MUST be a named setting with a default equal to today's behavior, overridable by an environment variable.
- **FR-026**: Invalid setting values MUST prevent startup with a message naming the setting.
- **FR-027**: All settings, their defaults, and their environment variable names MUST be documented in one place.

### Key Entities

- **Icon Position**: A service's hand-placed position within its box (per SKU selection); absent means "use default placement".
- **Active Snapshot**: The snapshot date every pricing lookup uses, whether it is pinned by the override, when it was last checked, and any newer snapshot waiting (with the reason). Held in memory; recomputed at startup.
- **Issue**: A non-blocking problem shown to admins — a service with no icon (code, name, snapshot date, New flag), regions missing from the active snapshot, or a pinned snapshot that lacks completion markers. Recomputed by each analysis.
- **Setting**: A named operational value with a default and an environment-variable override.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On every seeded architecture, 100% of icons are 2.5× their previous size and no two icons are closer than the minimum spacing under default placement.
- **SC-002**: After any sequence of drags, 0 icons overlap another icon and 0 icons lie outside or clipped by their box.
- **SC-003**: Hand-placed icon positions are identical before and after a page reload in 100% of cases.
- **SC-004**: 100% of errors appear in exactly one column — the one where the action was taken.
- **SC-005**: In 100% of top-level collection additions where the new box fits in the visible canvas, it appears fully in view; where free space exists, it overlaps no existing box.
- **SC-006**: 0 pricing lookups read a snapshot that lacks its completion marker in any table, unless an administrator has pinned that snapshot via the override (FR-018), in which case the Issues table shows a warning.
- **SC-007**: A newly completed snapshot becomes active, and any service in it with no icon appears in the Issues table, within one check interval (default: 5 minutes).
- **SC-007a**: With no pricing data change, 0 icon analyses run between restarts.
- **SC-008**: 100% of the backend's operational values can be changed via environment variable without code changes, and with none set the app behaves exactly as before.

## Assumptions

- "2.5× larger" applies to today's icon size (24px in canvas units → 60px), at every zoom level.
- Hand-placed icon positions are saved per browser, like box positions and sizes today (not shared with other users or included in architecture export/import).
- Only services shown as icons inside boxes can be dragged; a service attached to a connector is not affected.
- The Issues table is read-only; resolving an issue means updating the icon mapping and redeploying — the table has no actions.
- "An icon can be linked" uses the same icon mapping the canvas uses, so the Issues table and the canvas always agree on which services fall back to the generic icon.
- The upstream pricing job writes a `_SUCCESS` completion marker into each table's snapshot-date folder as its last step, and rewrites it when it updates a snapshot in place.
- Stored pricing results (015) are not flagged when a newer snapshot becomes active; the Data Timestamp shows which snapshot a result used, and Calculate always uses the active snapshot.
- An icon issue is marked "New" when its service code does not appear in the next-older snapshot date present in the pricing data (markers not required), so the marker is the same before and after a restart.
- Persisting monitoring state across restarts (e.g. the previously active date) is out of scope; a state table is planned for a future feature.
- One background service handles both the active-date check and the icon analysis; the backend runs as a single process (no coordination across multiple servers is needed in this feature).
- "Configurations" means backend operational values; frontend presentational constants (sizes, colors) are not in scope.
- The pop-up's attribute labels use the attribute names exactly as listed (e.g. `databaseEngine: MySQL`).
- The spacing rule applies to default placement and to drops; a user can't place two icons closer than the minimum by hand.
