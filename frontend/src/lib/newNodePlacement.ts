/**
 * Where a newly created top-level box goes on the canvas (016-canvas-icon-layout, FR-013,
 * research.md §11). Before this, new boxes took the next slot of a fixed grid regardless of what
 * the user was looking at, so they could land off-screen and seem not to have been created.
 *
 * Pure: all rects are in flow (canvas) coordinates. Scans the visible area left-to-right,
 * top-to-bottom for the first spot where the whole box is visible and clear of every existing
 * box (with a margin); when there's none, it uses the visible top-left — overlapping, but in view.
 */

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

function intersects(a: Rect, b: Rect, margin: number): boolean {
  return (
    a.x < b.x + b.width + margin &&
    a.x + a.width + margin > b.x &&
    a.y < b.y + b.height + margin &&
    a.y + a.height + margin > b.y
  );
}

export function findVisibleSlot(
  visible: Rect,
  occupied: Rect[],
  size: { width: number; height: number },
  margin = 24,
): Rect {
  const fits =
    size.width + 2 * margin <= visible.width && size.height + 2 * margin <= visible.height;
  if (!fits) return { x: visible.x, y: visible.y, ...size };

  const start = { x: visible.x + margin, y: visible.y + margin };
  const maxX = visible.x + visible.width - margin - size.width;
  const maxY = visible.y + visible.height - margin - size.height;
  for (let y = start.y; y <= maxY; y += size.height + margin) {
    for (let x = start.x; x <= maxX; x += size.width + margin) {
      const candidate = { x, y, ...size };
      if (!occupied.some((o) => intersects(candidate, o, margin))) return candidate;
    }
  }
  return { ...start, ...size };
}
