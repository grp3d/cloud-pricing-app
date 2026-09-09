# Feature Specification: Resizable Canvas & Reliable Box Sizing

**Feature Branch**: `005-resizable-canvas-boxes`

**Created**: 2026-09-08

**Status**: Draft

**Input**: User description: "2 visual issues - (1) the architecture window should be resizeable
within the web page (2) any entry in the architecture window needs to resize so all text within
the entry is visible"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Resize the assembly canvas to fit the available space (Priority: P1)

A user can resize the assembly canvas's visible area within the page, so they can see more of
their Architecture at once instead of being stuck panning and scrolling inside a small,
fixed-size window.

**Why this priority**: As an Architecture grows — more Collections, nested components, taller
boxes — a fixed-size canvas becomes actively cramped, undermining the diagram's whole purpose of
giving an at-a-glance view. This is a basic usability gap, not cosmetic polish.

**Independent Test**: On the assembly canvas page, drag to resize the canvas area larger and
smaller, and verify the visible canvas area changes size accordingly and remains fully usable
(panning, zooming, selecting, connecting) at the new size.

**Acceptance Scenarios**:

1. **Given** the assembly canvas at its default size, **When** the user drags to resize it,
   **Then** the visible canvas area grows or shrinks to match.
2. **Given** a resized canvas, **When** the user interacts with it (pans, zooms, selects a box,
   selects a connector), **Then** every existing canvas interaction continues to work correctly.
3. **Given** a resized canvas, **When** the user reloads the page, **Then** the canvas returns to
   its default size (consistent with how box position and size already behave — see
   Assumptions).

---

### User Story 2 - A box's text is never clipped or overlapping (Priority: P1)

Every box on the assembly canvas — Application Components and VPCs — reliably resizes so that
all of its text content is fully visible, no matter how much identifying detail a service's
description line contains or how many services a box holds.

**Why this priority**: `004-canvas-pricing-improvements` sized boxes from an *estimate* of their
content, not their actual rendered size — this reliably works for short content but leaves a real
gap for longer text, defeating the purpose of showing identifying detail at all if it gets cut
off. This is a correctness fix, not new functionality.

**Independent Test**: Add a service with a long identifying-detail line to a box (so its detail
text would wrap to more than one line) and verify the box grows to fully show it, with no text
clipped and no overlap with a nested or neighboring box.

**Acceptance Scenarios**:

1. **Given** a box contains a service whose identifying-detail text is long enough to wrap to
   multiple lines, **When** the user views the canvas, **Then** the box is tall enough to show
   that service's text in full, not clipped.
2. **Given** a box's content changes (a service is added, removed, or a longer/shorter one
   replaces another), **When** the canvas updates, **Then** the box's size adjusts to keep
   showing its full content, growing or shrinking as needed.
3. **Given** a box is nested inside another box, **When** the inner box needs more height to
   show its full text, **Then** the outer box also grows to keep fully containing it (consistent
   with the cascading behavior already established in `004-canvas-pricing-improvements`).

---

### Edge Cases

- What's the smallest the assembly canvas can be resized to? It stays large enough to remain
  usable — the resize action itself and the canvas's basic controls stay reachable and operable
  at any size a user resizes it to.
- What happens to a box's manually-resized size (an existing capability from
  `004-canvas-pricing-improvements`) when its content changes? Unchanged from `004`: content-fit
  sizing supersedes a prior manual size on the next content change, since a manual size must
  never end up hiding content that no longer fits it.
- What happens when a box's content is short? It stays at whatever size actually fits that
  content — this feature doesn't force boxes to be larger than they need to be, only guarantees
  they're never smaller than they need to be.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Users MUST be able to resize the assembly canvas's visible area within the page.
- **FR-002**: The assembly canvas MUST remain fully functional — panning, zooming, selecting a
  box or connector, dragging, resizing an individual box — at any size the user resizes it to.
- **FR-003**: A box's size on the assembly canvas MUST always be sufficient to show all of its
  current text content without any of it being clipped or hidden, regardless of how long that
  content is or how many lines it wraps to.
- **FR-004**: A box's size MUST update automatically whenever its content changes in a way that
  changes how much space that content actually needs.
- **FR-005**: When a box that is nested inside another box needs more space to show its content,
  the containing box MUST also grow as needed to keep fully showing it, however many levels of
  nesting are involved (carried forward from `004-canvas-pricing-improvements`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can resize the assembly canvas to fit their available screen space in a
  single drag gesture.
- **SC-002**: No box's text is ever clipped, cut off, or overlapping with another box's content,
  regardless of how much text that box currently contains.
- **SC-003**: Resizing the canvas or a box never breaks any existing canvas interaction (panning,
  zooming, selecting, connecting, dragging, nesting).

## Assumptions

- The assembly canvas's resized size is a per-session, per-view convenience — it is not saved
  and resets to its default on the next page load, consistent with how box position and size
  already behave (established in `001`-`004`).
- This feature fixes box *height* reliability (never clipping text). Box *width* remains
  user-resizable as already established in `004`, but is not required to grow automatically —
  taller boxes (via wrapped text) are the expected way content stays fully visible, not wider
  ones.
- This feature does not change what information is shown in a box (that's
  `003`/`004`'s scope) — only that whatever is shown is reliably fully visible.
- This feature does not introduce new nesting capabilities or new duration/pricing behavior —
  it is a sizing-reliability and canvas-viewport fix layered on top of `001`-`004`'s existing
  behavior.
