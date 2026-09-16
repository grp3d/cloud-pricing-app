# Feature Specification: Canvas Connector & Pop-Out Improvements

**Feature Branch**: `011-canvas-connector-popout`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "see docs/functionality_2026-09-16.md"

## Clarifications

### Session 2026-09-16

- Q: Should the canvas pop-out (FR-008) open as a real separate browser window, or as an enlarged overlay/modal that stays inside the same browser tab? → A: In-tab overlay/modal — the canvas enlarges within the same browser tab (e.g. a large resizable dialog over columns 2-4), sharing state directly with columns 2/3 with no cross-window messaging, popup-blocker risk, or ability to move it to a second monitor/OS taskbar entry.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pop out the architecture canvas into its own view (Priority: P1)

A user configuring an architecture wants to see the full diagram at a larger size while they keep working in the service search (column 2) and Service Editor (column 3), rather than being limited to column 4's narrow default width.

**Why this priority**: This is the most novel, highest-value capability in this feature set — it removes the canvas's biggest usability constraint (limited screen real estate) without disrupting the rest of the workflow.

**Independent Test**: Can be fully tested by opening the pop-out from column 4, adding a Service or Connector via columns 2/3, confirming the change appears in the pop-out without a manual refresh, then closing the pop-out and confirming column 4's own canvas is fully usable again.

**Acceptance Scenarios**:

1. **Given** an architecture is open in the workspace, **When** the user clicks the pop-out icon in the top-right corner of column 4's canvas, **Then** an enlarged, adjustable view of the same canvas opens.
2. **Given** the pop-out is open, **When** the user adds, edits, or removes a Collection, Connector, or Service via columns 2/3, **Then** the pop-out's canvas reflects that change without the user needing to manually refresh or re-open it.
3. **Given** the pop-out is open, **When** the user closes it, **Then** column 4's own canvas becomes the active view again, showing the architecture's current state.
4. **Given** the pop-out is open, **When** the user resizes it, **Then** the canvas within it adjusts to make use of the new size.

---

### User Story 2 - One consistent way to create a Connector (Priority: P2)

A user wants a single, predictable way to connect two Collections, whether they've already selected them on the canvas or not, instead of two different controls with two different behaviors (one that connects immediately, one that opens a picker).

**Why this priority**: Consolidates duplicate functionality and removes a source of confusion (two buttons, two behaviors, one purpose) — meaningful workflow cleanup, but lower-impact than the pop-out itself.

**Independent Test**: Can be fully tested by selecting zero, one, and two Collections on the canvas in turn, clicking "Connect" in column 2 each time, and confirming the resulting dialog's From/To dropdowns are pre-populated accordingly and that no Connector is created until the user explicitly confirms.

**Acceptance Scenarios**:

1. **Given** no Collections are selected on the canvas, **When** the user clicks "Connect" in column 2, **Then** a dialog opens with empty "From Collection" and "To Collection" dropdowns, matching today's column 4 "Add Connector" dialog.
2. **Given** exactly one Collection is selected on the canvas, **When** the user clicks "Connect" in column 2, **Then** the dialog opens with "From Collection" pre-populated with that Collection and "To Collection" left for the user to choose.
3. **Given** exactly two Collections are selected on the canvas (in selection order), **When** the user clicks "Connect" in column 2, **Then** the dialog opens with "From Collection" and "To Collection" pre-populated with the first and second selected Collections respectively.
4. **Given** the dialog is open with both dropdowns pre-populated, **When** the user does nothing further, **Then** no Connector is created — the user must still click "Add Connector" in the dialog to confirm.
5. **Given** the feature is implemented, **When** the user looks at column 4's canvas, **Then** there is no standalone "Add Connector" button on the canvas itself — column 2's "Connect" button is the only entry point.

---

### User Story 3 - More legible canvas text (Priority: P3)

A user viewing the architecture canvas in column 4 wants the Collection, Connector, and region-label text to be easier to read at the diagram's default zoom level.

**Why this priority**: A real but low-risk legibility polish item, independent of the other two stories.

**Independent Test**: Can be fully tested by opening any architecture with Collections and Connectors and confirming the canvas text is larger than the current default while the diagram's zoom level itself is unchanged.

**Acceptance Scenarios**:

1. **Given** an architecture with at least one Collection is open, **When** the user views column 4's canvas at its default zoom level, **Then** Collection/Connector/region-label text is larger than the current default and does not overflow or clip its containing box.

---

### Edge Cases

- Exactly one Collection selected when "Connect" is clicked → dialog opens with only "From Collection" pre-populated; "To Collection" is left for the user to choose (US2).
- More than two Collections selected when "Connect" is clicked → dialog opens with both dropdowns empty, the same as today's zero-selection column 4 behavior, since pre-population is only defined for the 0/1/2-selected cases.
- User tries to open a second pop-out while one is already open → the existing pop-out is brought into focus rather than a second one being created.
- The pop-out is dismissed by a means other than its explicit close button (e.g. pressing Escape) → treated the same as closing it; column 4's canvas resumes as the active view without requiring a full page reload. Clicking outside the pop-out does *not* close it — per FR-011/the resolved Clarification, "outside" is column 4's own live canvas, and a click there is an interaction with it, not a request to dismiss the pop-out (implementation note added during `/speckit-implement`: this refines the earlier draft of this edge case, which assumed a modal backdrop before finding F1 was resolved).
- The user reloads or navigates away from the page while the pop-out is open → the pop-out does not need to be restored on return, matching how the app's other in-page dialogs already behave.
- Data referenced by the pop-out's canvas changes in a way that invalidates it while open (e.g. a Collection shown in the pop-out is deleted) → the pop-out reflects the same removal/update that column 4's canvas would show.
- Larger canvas text must not cause label text to overflow or clip within Collection/Connector boxes at the diagram's default zoom (004/008's prior narrow-column overflow issue is the relevant precedent).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The architecture canvas in column 4 MUST render Collection names, Connector labels, and region labels at a larger text size than the current default, without changing the diagram's default zoom level.
- **FR-002**: The standalone "Add Connector" button/dialog currently on column 4's canvas MUST be removed; connector creation from the canvas selection flow moves entirely to the "Connect" button in column 2 (FR-003–FR-006).
- **FR-003**: Clicking "Connect" in column 2 MUST open a dialog with "From Collection" and "To Collection" dropdowns, the same dialog pattern currently used by column 4's "Add Connector" button, rather than immediately creating a Connector.
- **FR-004**: The "Connect" button in column 2 MUST be enabled regardless of how many Collections are currently selected on the canvas (previously it required exactly two).
- **FR-005**: When the dialog opens, it MUST pre-populate "From Collection" and, if a second Collection is selected, "To Collection" from the Collections currently selected on the canvas, in selection order; if zero Collections are selected, both dropdowns open empty.
- **FR-006**: A Connector MUST NOT be created until the user explicitly clicks "Add Connector" inside the dialog, even when both dropdowns are already pre-populated.
- **FR-007**: Column 4's canvas MUST show a pop-out control (a [↗]-style icon) in its top-right corner.
- **FR-008**: Clicking the pop-out control MUST open an adjustable (resizable and movable), enlarged in-app overlay — within the same browser tab, not a separate browser window — showing the same architecture canvas as column 4.
- **FR-008a**: The pop-out MUST be repositionable (drag-to-move) within the browser window, so the user can move it clear of columns 1–3 while it's open (live user report, added after initial implementation: the original design assumed repositioning wasn't needed, but without it the pop-out's own default size unavoidably covers those columns).
- **FR-009**: While the pop-out is open, any change made via columns 2/3 (adding/editing/removing Collections, Connectors, or Service Selections; region changes) MUST be reflected in the pop-out's canvas without the user manually refreshing or reopening it.
- **FR-010**: Closing the pop-out MUST return column 4's own canvas to being the active view, showing the architecture's current state.
- **FR-011**: While the pop-out is open, column 4's own canvas MUST remain a live, independently-interactive mirror of the same architecture — showing the same up-to-date diagram and remaining fully usable on its own (selecting, connecting, etc.) — rather than becoming a disabled or placeholder view. "Independently-interactive" refers to input handling (both canvases can be clicked/dragged/panned on their own), not to selection state — see FR-011a.
- **FR-011a**: Selecting a Collection, Connector, or Service in either canvas (column 4's or the pop-out's) MUST select the same one in the other canvas too, and MUST update columns 2/3 exactly as column 4's own selection already does — the two canvases share one selection, not two independent ones (follow-up, confirmed against a user-supplied reference screenshot showing a pop-out selection reflected in columns 2/3; supersedes the original FR-011/research.md §3 framing of "independent" selection).

### Key Entities

*(No new or changed data entities — this feature is presentation-layer only and reuses the existing Collection/Connector data and connector-creation operation.)*

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can read every Collection, Connector, and region label on the architecture canvas at its default zoom level without needing to zoom in first.
- **SC-002**: When a user has already selected the two Collections they want to connect on the canvas, creating the Connector takes exactly one additional confirmation click (opening the dialog and confirming), with no need to re-select either Collection in the dialog.
- **SC-003**: At any time, the workspace shows exactly one control for creating a Connector, eliminating the prior duplication between column 2 and column 4.
- **SC-004**: Users can keep editing Services and Connectors in columns 2/3 while viewing an enlarged version of the canvas, with those edits visible in the enlarged view within a few seconds and without a manual refresh.
- **SC-005**: Closing the enlarged canvas view always returns the user to a fully functional main canvas, with no data loss and no page reload required.

## Assumptions

- The font-size increase in User Story 3 is the next increment beyond the size already in place today (this feature captures the desired end state; it does not assume any specific starting point).
- "Adjustable" for the pop-out means user-resizable, consistent with the resize patterns already used elsewhere in the workspace (e.g. column widths, diagram panel height). ~~Free repositioning/dragging around the screen is not required~~ — superseded by FR-008a after live use showed the pop-out's own default size otherwise unavoidably covers columns 1–3, making them unreachable while it's open.
- The From/To pre-population order in User Story 2 follows the same selection-order logic the app already uses elsewhere for the existing two-Collection connect flow.
- No backend/API changes are required — both changes are presentation-layer only, reusing the existing connector-creation operation and already-loaded architecture data.
- The pop-out reflects only the current user's own session; no multi-user/real-time collaboration behavior is implied.
