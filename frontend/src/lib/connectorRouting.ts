/**
 * Pure geometry logic for auto-choosing which side of each Collection box a new Connector
 * attaches to (009-ui-fixes-next-iteration follow-up, new arch spec requirement). Given two
 * boxes' rects and how many Connectors each of their four sides already carries, picks:
 *
 * 1. The side giving the shortest path between the boxes ("shortest path" = the side whose
 *    own midpoint is geometrically closest to the other box's center — the natural measure
 *    of how direct a straight connecting line through that side would be) —
 * 2. ...but only among sides with *no* Connector on them yet, if any such side exists;
 * 3. Falling back to *every* side already occupied: the side with the fewest Connectors,
 *    tie-broken by shortest path.
 *
 * No DOM/React Flow dependency, matching `dropTargetDetection.ts`/`nodeLayout.ts`'s
 * precedent — `ArchitectureDiagramPanel.tsx` is the only caller, supplying real node rects
 * and per-side usage counts derived from `lib/connectorSides.ts`'s persisted assignments.
 */

export type ConnectorSide = "top" | "right" | "bottom" | "left";

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export const ALL_CONNECTOR_SIDES: readonly ConnectorSide[] = ["top", "right", "bottom", "left"];

/** Type guard for a value that came from somewhere untyped — a stored `localStorage` entry
 * (`connectorSides.ts`), or a React Flow `Connection`'s `sourceHandle`/`targetHandle` (typed
 * as `string | null | undefined` since React Flow itself doesn't know this app's handle ids
 * are always one of these four). */
export function isConnectorSide(value: unknown): value is ConnectorSide {
  return value === "top" || value === "right" || value === "bottom" || value === "left";
}

export interface Point {
  x: number;
  y: number;
}

function center(rect: Rect): Point {
  return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
}

function sideMidpoint(rect: Rect, side: ConnectorSide): Point {
  switch (side) {
    case "top":
      return { x: rect.x + rect.width / 2, y: rect.y };
    case "bottom":
      return { x: rect.x + rect.width / 2, y: rect.y + rect.height };
    case "left":
      return { x: rect.x, y: rect.y + rect.height / 2 };
    case "right":
      return { x: rect.x + rect.width, y: rect.y + rect.height / 2 };
  }
}

function distance(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

/** All four sides of `rect`, ordered by shortest path to `otherCenter` (ascending distance
 * from that side's own midpoint) — index 0 is the single best ("shortest path") side. */
function rankSidesByPath(rect: Rect, otherCenter: Point): ConnectorSide[] {
  return [...ALL_CONNECTOR_SIDES].sort(
    (a, b) =>
      distance(sideMidpoint(rect, a), otherCenter) - distance(sideMidpoint(rect, b), otherCenter),
  );
}

/** Picks one side for a box from its shortest-path-ranked sides and how many Connectors each
 * already carries: the highest-ranked *unoccupied* side if one exists, otherwise the
 * least-occupied side — `Array.prototype.sort` is stable (ES2019+), so sorting the
 * already-shortest-path-ordered list by usage count preserves that order among ties,
 * satisfying "fewest connectors, then shortest path" exactly. */
function pickSide(rankedSides: ConnectorSide[], usage: Record<ConnectorSide, number>): ConnectorSide {
  const open = rankedSides.find((side) => (usage[side] ?? 0) === 0);
  if (open) return open;
  return [...rankedSides].sort((a, b) => (usage[a] ?? 0) - (usage[b] ?? 0))[0];
}

/** Chooses which side of `fromRect` and which side of `toRect` a new Connector between them
 * should attach to, per the module doc above. `fromUsage`/`toUsage` are each box's *current*
 * per-side Connector counts (excluding the Connector being placed, if any). */
export function chooseConnectorSides(
  fromRect: Rect,
  toRect: Rect,
  fromUsage: Record<ConnectorSide, number>,
  toUsage: Record<ConnectorSide, number>,
): { fromSide: ConnectorSide; toSide: ConnectorSide } {
  const fromCenter = center(fromRect);
  const toCenter = center(toRect);
  return {
    fromSide: pickSide(rankSidesByPath(fromRect, toCenter), fromUsage),
    toSide: pickSide(rankSidesByPath(toRect, fromCenter), toUsage),
  };
}

/** Live user report: Connector lines could be drawn straight through an unrelated Collection
 * box sitting between the two boxes they actually connect. `routeAroundObstacles` (used by
 * `ArchitectureDiagramPanel.tsx`'s `OffsetEdge`) detects that and returns a short detour
 * instead, so a Connector never visually crosses a box it isn't attached to. */

/** Margin (px) kept clear between a routed Connector and an obstacle box's own edge — a purely
 * visual buffer so the line reads as "going around" rather than grazing the border. */
const OBSTACLE_MARGIN = 16;

/** True if the segment from `(x1,y1)` to `(x2,y2)` enters `rect` (expanded by `margin` on
 * every side) anywhere along its length, including at either endpoint — the standard
 * Liang-Barsky segment/AABB clipping test, used here purely as a boolean intersection check
 * rather than to compute the clipped sub-segment itself. */
function segmentIntersectsRect(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  rect: Rect,
  margin: number,
): boolean {
  const rx0 = rect.x - margin;
  const ry0 = rect.y - margin;
  const rx1 = rect.x + rect.width + margin;
  const ry1 = rect.y + rect.height + margin;
  const dx = x2 - x1;
  const dy = y2 - y1;
  let tMin = 0;
  let tMax = 1;

  // Clips the segment's parametric range [tMin, tMax] against one of the rect's four
  // half-plane boundaries; returns false the moment the range becomes empty (a definitive
  // "doesn't intersect", short-circuiting the remaining boundaries).
  function clip(p: number, q: number): boolean {
    if (p === 0) return q >= 0;
    const r = q / p;
    if (p < 0) {
      if (r > tMax) return false;
      if (r > tMin) tMin = r;
    } else {
      if (r < tMin) return false;
      if (r < tMax) tMax = r;
    }
    return true;
  }

  return (
    clip(-dx, x1 - rx0) &&
    clip(dx, rx1 - x1) &&
    clip(-dy, y1 - ry0) &&
    clip(dy, ry1 - y1) &&
    tMin <= tMax
  );
}

/**
 * Given a straight line from `source` to `target`, finds which of `obstacles` it actually
 * crosses and, if any do, returns a short polyline route around their combined bounding box
 * instead of the straight line — `null` if the straight line is already clear of every
 * obstacle, so the caller keeps using its own default curve/bezier for the (overwhelmingly
 * common) unobstructed case.
 *
 * The detour goes around whichever side — top/bottom if the line is more horizontal than
 * vertical, left/right if more vertical — the straight line's own midpoint already sits
 * closer to, so it takes the shorter of the two ways around, then steps out, across, and back
 * in (a 4-point "U"/"Z" shape) rather than cutting the corner. `extraOffset` (default 0) pushes
 * the detour further from the obstacle by that many additional pixels, always outward
 * regardless of which side was chosen — for disambiguating multiple parallel Connectors that
 * all need to detour around the same obstacle, the same way `OffsetEdge`'s own perpendicular
 * offset already disambiguates parallel *unobstructed* Connectors.
 *
 * Handles the common case — one or a few boxes sitting between two others that are roughly
 * grid-aligned — robustly; not a general-purpose pathfinder, so a dense, irregular cluster of
 * overlapping boxes isn't guaranteed a fully clear route.
 */
export function routeAroundObstacles(
  source: Point,
  target: Point,
  obstacles: Rect[],
  extraOffset = 0,
): Point[] | null {
  const blocking = obstacles.filter((rect) =>
    segmentIntersectsRect(source.x, source.y, target.x, target.y, rect, OBSTACLE_MARGIN),
  );
  if (blocking.length === 0) return null;

  const left = Math.min(...blocking.map((r) => r.x));
  const top = Math.min(...blocking.map((r) => r.y));
  const right = Math.max(...blocking.map((r) => r.x + r.width));
  const bottom = Math.max(...blocking.map((r) => r.y + r.height));

  const dx = target.x - source.x;
  const dy = target.y - source.y;

  if (Math.abs(dx) >= Math.abs(dy)) {
    const midY = (source.y + target.y) / 2;
    const detourAboveTop = midY - top <= bottom - midY;
    const detourY = detourAboveTop
      ? top - OBSTACLE_MARGIN - extraOffset
      : bottom + OBSTACLE_MARGIN + extraOffset;
    return [source, { x: source.x, y: detourY }, { x: target.x, y: detourY }, target];
  }

  const midX = (source.x + target.x) / 2;
  const detourLeftOfLeft = midX - left <= right - midX;
  const detourX = detourLeftOfLeft
    ? left - OBSTACLE_MARGIN - extraOffset
    : right + OBSTACLE_MARGIN + extraOffset;
  return [source, { x: detourX, y: source.y }, { x: detourX, y: target.y }, target];
}
