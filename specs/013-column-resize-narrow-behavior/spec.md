# Feature Specification: Architecture Panel Narrow-Width Layout

**Feature Branch**: `013-column-resize-narrow-behavior`

**Created**: 2026-09-18

**Status**: Draft

**Input**: User description: "in column 1 of the cloud pricing tab, when the column is resized and made narrower, the entry form for the new architecture name should be narrowed before the create button is hidden. The action buttons (import architecture, share arch, delete arch, create arch) should remain visible when the user narrows the column. The listed architectures should word wrap (the way the 'AWS Architectures' text word wraps when the column is manually narrowed). The collapse/expand behavior is fine as-is."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create form shrinks instead of losing its button (Priority: P1)

A user drags the architecture panel's resize handle to make it narrower. As the panel narrows, the "New Architecture" name field shrinks in width to fit the available space, and the Create button stays fully visible and clickable at every width down to the panel's minimum resizable width.

**Why this priority**: Creating a new architecture is a core action available directly in this panel. If the Create button disappears or becomes unreachable, the user loses the ability to create an architecture without first widening the panel back out — the most disruptive possible regression from resizing.

**Independent Test**: Can be fully tested by dragging the panel to its narrowest width and confirming the Create button is still fully visible and clickable, while the name input has visibly shrunk.

**Acceptance Scenarios**:

1. **Given** the architecture panel is at its default or a wide width, **When** the user drags the resize handle to narrow the panel, **Then** the "New Architecture" name input's width decreases before any part of the Create button is affected.
2. **Given** the architecture panel has been narrowed to its minimum resizable width, **When** the user looks at the new-architecture entry row, **Then** the Create button remains fully visible and clickable, and the name input is still present (even if narrow) rather than removed or clipped.

---

### User Story 2 - Action buttons stay visible while narrowing (Priority: P1)

A user narrows the architecture panel. The import-architecture button, and each listed architecture's share and delete buttons, remain visible and clickable throughout the resize, at any width down to the panel's minimum resizable width.

**Why this priority**: Import, share, and delete are the other primary actions available from this panel. Losing access to them during normal resizing blocks routine architecture management just as much as losing the Create button would.

**Independent Test**: Can be fully tested by narrowing the panel to its minimum width and confirming the import button and every visible row's share/delete buttons are still present and clickable, with no button clipped off or overlapping another control.

**Acceptance Scenarios**:

1. **Given** the architecture panel is expanded and showing at least one architecture, **When** the user narrows the panel to its minimum resizable width, **Then** the import button and every row's share and delete buttons remain fully visible and clickable.
2. **Given** the panel is at its minimum resizable width, **When** the user narrows further (if the drag handle allows it) or the layout is at its tightest point, **Then** the action buttons never become hidden, cut off, or unusably overlapped by other controls — the architecture name area yields space first.

---

### User Story 3 - Architecture names word-wrap instead of truncating (Priority: P2)

A user narrows the architecture panel while it lists one or more architectures. Architecture names that no longer fit on one line wrap onto additional lines, the same way the "AWS Architectures" heading already wraps, instead of being cut off with an ellipsis or clipped.

**Why this priority**: Being able to read the full name of each architecture is valuable but secondary to keeping actions usable (User Stories 1 and 2) — a wrapped name is a readability improvement, not a blocked action.

**Independent Test**: Can be fully tested by creating an architecture with a long name, narrowing the panel until the name no longer fits on one line, and confirming the full name is visible across multiple wrapped lines rather than ending in an ellipsis.

**Acceptance Scenarios**:

1. **Given** an architecture with a name too long to fit the current panel width on one line, **When** the panel is at that width, **Then** the full name is visible, wrapped across multiple lines, with no ellipsis truncation and no clipped text.
2. **Given** a row whose name has wrapped onto multiple lines, **When** the user views that row, **Then** the row's share and delete buttons are still fully visible and aligned with the row, not pushed out of view by the taller, wrapped name.

---

### Edge Cases

- What happens when the panel is narrowed all the way to its minimum resizable width (equal to the collapsed-rail width) while architectures with long names are listed? All action buttons (import, per-row share/delete, and Create) must still be fully visible; only the name text area shrinks and/or wraps.
- How does the system handle a name so long that even wrapped text plus the buttons cannot fully fit at the minimum width? The row's action buttons take priority for visibility over showing the entire name on few lines; the name area continues to wrap onto as many lines as needed rather than the buttons yielding space.
- What happens to the "New Architecture" name input at the minimum resizable width? It remains visible at a reduced (but non-zero) width rather than being removed from the layout, and the Create button keeps its normal size (never shrinks or loses its label). At widths too narrow to fit both the input and the button on one line, the button may move to its own line directly below the input rather than being clipped — it must never be cut off, overlapped, or scrolled out of view.
- Does narrowing the panel change collapse/expand behavior? No — collapsing and expanding the panel continue to work exactly as they do today; this feature only changes how content lays out while the panel is expanded and being resized.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When the architecture panel is narrowed, the "New Architecture" name entry field MUST decrease in width to fit the available space before the Create button's visibility or size is affected in any way.
- **FR-002**: The Create button MUST remain fully visible and clickable at every panel width the resize handle allows, including the panel's minimum resizable width.
- **FR-003**: The import-architecture button MUST remain fully visible and clickable at every panel width the resize handle allows, including the minimum resizable width.
- **FR-004**: Each listed architecture's share button and delete button MUST remain fully visible and clickable at every panel width the resize handle allows, including the minimum resizable width.
- **FR-005**: When an architecture's name does not fit on one line at the current panel width, the system MUST wrap the name onto additional lines instead of truncating it with an ellipsis or clipping it.
- **FR-006**: When an architecture name wraps onto multiple lines, the row's share and delete buttons MUST remain fully visible and correctly aligned with that row.
- **FR-007**: Narrowing or widening the panel MUST NOT change the panel's existing collapse/expand behavior or controls.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At every panel width between the maximum and minimum resizable width, 100% of action buttons (import, create, and each row's share/delete) remain visible and clickable — none disappear, clip, or become unreachable.
- **SC-002**: When narrowing the panel from a wide state to its minimum resizable width, the "New Architecture" name field's visible width decreases measurably before the Create button's size or position changes at all.
- **SC-003**: Architecture names that exceed the available row width display their complete text via wrapping, with 0% of names showing an ellipsis or clipped characters, across all panel widths down to the minimum resizable width.
- **SC-004**: Users can successfully create, import, share, and delete architectures while the panel is at its minimum resizable width, with the same success rate as at the default panel width.

## Assumptions

- The panel's existing minimum resizable width (the width the drag handle already clamps to, matching the collapsed-rail width) is not being changed by this feature — only how content lays out within that existing range is changing.
- "Word wrap" for architecture names means multi-line text wrapping at word/character boundaries within the available width, matching the visual behavior already used by the "AWS Architectures" heading — no new truncation indicator (e.g., a tooltip or "show more" control) is introduced.
- When space is tightest, the architecture name area is the element expected to shrink and wrap; the action buttons (import, create, share, delete) keep their current fixed size rather than shrinking themselves.
- Collapse/expand behavior and its own minimum/rail width are explicitly out of scope for changes — only the resize (drag-to-narrow) experience while expanded is affected.
