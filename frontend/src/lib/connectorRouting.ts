/**
 * Pure geometry logic for auto-choosing which side of each Collection box a new Connector
 * attaches to (009-ui-fixes-next-iteration follow-up, new arch spec requirement).
 *
 * Live user rule change: it's fine for multiple Connectors to depart a Collection from the
 * same side now, so the *departure* side (`fromSide`) is always simply whichever side gives
 * the shortest path to the other Collection ("shortest path" = the side whose own midpoint is
 * geometrically closest to the other box's center) — no occupancy consideration at all
 * anymore. The *arrival* side (`toSide`) keeps the original rule, since that one still governs
 * how many arrowheads visually cluster on one side of a box:
 *
 * 1. The shortest-path side —
 * 2. ...but only among sides with *no* Connector already pointing at them, if any such side
 *    exists;
 * 3. Falling back to *every* side already occupied: the side with the fewest Connectors
 *    pointing at it, tie-broken by shortest path.
 *
 * No DOM/React Flow dependency, matching `dropTargetDetection.ts`/`nodeLayout.ts`'s
 * precedent — `ArchitectureDiagramPanel.tsx` is the only caller, supplying real node rects
 * and per-side "how many Connectors already point at this side" counts derived from
 * `lib/connectorSides.ts`'s persisted assignments (counting only `to` assignments now — see
 * `resolveConnectorSides`).
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
 * should attach to, per the module doc above. `toUsage` is `toRect`'s *current* per-side count
 * of Connectors already pointing at it (excluding the Connector being placed, if any). */
export function chooseConnectorSides(
  fromRect: Rect,
  toRect: Rect,
  toUsage: Record<ConnectorSide, number>,
): { fromSide: ConnectorSide; toSide: ConnectorSide } {
  const fromCenter = center(fromRect);
  const toCenter = center(toRect);
  return {
    fromSide: rankSidesByPath(fromRect, toCenter)[0],
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

/** How far (px) a detoured Connector's endpoint "stub" extends straight out from its own box,
 * in the handle's own outward direction, before bending toward the detour around whatever it's
 * avoiding — see `routeAroundObstacles`'s own doc comment for why this exists. */
const STUB_LENGTH = 28;

/** `point`, moved `distance` px outward from its own box in the direction `side` faces —
 * `top`/`bottom` move along y, `left`/`right` along x. Used to build a detoured Connector's
 * "stub" segments (`routeAroundObstacles`), which must leave/enter perpendicular to the box's
 * actual attached side for the arrowhead to render pointing into the box, not at some
 * unrelated angle. */
export function offsetPoint(point: Point, side: ConnectorSide, distance: number): Point {
  switch (side) {
    case "top":
      return { x: point.x, y: point.y - distance };
    case "bottom":
      return { x: point.x, y: point.y + distance };
    case "left":
      return { x: point.x - distance, y: point.y };
    case "right":
      return { x: point.x + distance, y: point.y };
  }
}

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

/** A point on a cubic Bezier curve at parameter `t` (De Casteljau / the standard cubic Bezier
 * formula) — used to sample `getBezierPath`'s actual rendered curve for the obstacle check
 * below, not just its straight-line endpoints. */
function cubicBezierPoint(p0: Point, p1: Point, p2: Point, p3: Point, t: number): Point {
  const u = 1 - t;
  return {
    x: u * u * u * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t * t * t * p3.x,
    y: u * u * u * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t * t * t * p3.y,
  };
}

/** `steps + 1` evenly-spaced points along the cubic Bezier curve from `p0` to `p3` (control
 * points `p1`/`p2`), inclusive of both endpoints. */
export function sampleCubicBezier(p0: Point, p1: Point, p2: Point, p3: Point, steps: number): Point[] {
  const points: Point[] = [];
  for (let i = 0; i <= steps; i++) {
    points.push(cubicBezierPoint(p0, p1, p2, p3, i / steps));
  }
  return points;
}

/** Same as `sampleCubicBezier` but for a quadratic Bezier (one control point) — matches the
 * `Q` curve `OffsetEdge` draws for its own parallel-Connector perpendicular-offset paths. */
export function sampleQuadraticBezier(p0: Point, control: Point, p2: Point, steps: number): Point[] {
  const points: Point[] = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const u = 1 - t;
    points.push({
      x: u * u * p0.x + 2 * u * t * control.x + t * t * p2.x,
      y: u * u * p0.y + 2 * u * t * control.y + t * t * p2.y,
    });
  }
  return points;
}

/**
 * Given a straight line from `source` to `target`, finds which of `obstacles` it actually
 * crosses and, if any do, returns a short route around their combined bounding box instead of
 * the straight line — `null` if the line is already clear of every obstacle, so the caller
 * keeps using its own default curve/bezier for the (overwhelmingly common) unobstructed case.
 *
 * `pathSamples`, if given, is the sequence of points (including `source`/`target` as its first
 * and last entries) the caller's own *default* unobstructed curve would actually draw — e.g.
 * `sampleCubicBezier`'s output for `getBezierPath`'s curve. Live user report: testing only the
 * straight `source`→`target` line missed cases where that line was clear but the *rendered*
 * curve (React Flow's default bezier control-point placement bulges outward, especially for
 * `Position.Top`/`Position.Bottom` handles) swung through a box the straight line itself would
 * have missed. Every consecutive pair in `pathSamples` is checked, and every obstacle any pair
 * touches contributes to the combined bounding box below — not just whichever segment
 * (falling back to just `[source, target]` when omitted, matching the original straight-line-
 * only behavior every existing caller/test still relies on).
 *
 * `sourceSide`/`targetSide`, if given, are the actual attached side (`Position`, reused as
 * `ConnectorSide`) of each endpoint's own box. Live user report #2: without these, the detour's
 * first/last segments went straight from `source`/`target` to wherever the detour happened to
 * need, in a direction unrelated to the box's actual attached side — so a Connector detouring
 * to a `right`-side handle could approach it from directly above, for instance. Since the
 * arrowhead marker orients to the path's own tangent at its endpoint, that made arrows point in
 * whatever direction the detour geometry happened to produce, not into the box. When given,
 * each endpoint gets a short straight "stub" (`STUB_LENGTH` px, via `offsetPoint`) leaving/
 * entering perpendicular to its own side *before* the detour route starts/ends, guaranteeing
 * the final approach into `target` — and the marker orientation with it — always points
 * straight into the box along its actual attached side, the same as an ordinary unobstructed
 * Connector's `getBezierPath` curve already does via `targetPosition`. Omitting a side falls
 * back to using the raw point as its own "stub" (no perpendicular correction).
 *
 * The detour's middle "rail" goes around whichever side — top/bottom if the line is more
 * horizontal than vertical, left/right if more vertical — the straight line's own midpoint
 * already sits closer to, so it takes the shorter of the two ways around. `extraOffset`
 * (default 0) pushes the rail further from the obstacle by that many additional pixels, always
 * outward regardless of which side was chosen — for disambiguating multiple parallel
 * Connectors that all need to detour around the same obstacle, the same way `OffsetEdge`'s own
 * perpendicular offset already disambiguates parallel *unobstructed* Connectors.
 *
 * Handles the common case — one or a few boxes sitting between two others that are roughly
 * grid-aligned — robustly; not a general-purpose pathfinder, so a dense, irregular cluster of
 * overlapping boxes isn't guaranteed a fully clear route. Always returns exactly 6 points —
 * `[source, sourceStub, corner1, corner2, targetStub, target]` — meant to be drawn as two
 * straight stub segments (`source`→`sourceStub`, `targetStub`→`target`) bracketing a smooth
 * curve through the middle 4 (`OffsetEdge`'s choice) for a swooping-but-still-correctly-
 * oriented look; a Bezier curve never leaves the convex hull of its control points, and
 * `sourceStub`/`corner1`/`corner2`/`targetStub` already sit outside the obstacle by at least
 * `OBSTACLE_MARGIN`, so the curved middle stays clear in the same common cases this function
 * already targets.
 */
export function routeAroundObstacles(
  source: Point,
  target: Point,
  obstacles: Rect[],
  extraOffset = 0,
  pathSamples?: Point[],
  sourceSide?: ConnectorSide,
  targetSide?: ConnectorSide,
): Point[] | null {
  const points = pathSamples && pathSamples.length >= 2 ? pathSamples : [source, target];
  const blocking = obstacles.filter((rect) =>
    points.some((p, i) =>
      i === 0
        ? false
        : segmentIntersectsRect(points[i - 1].x, points[i - 1].y, p.x, p.y, rect, OBSTACLE_MARGIN),
    ),
  );
  if (blocking.length === 0) return null;

  const left = Math.min(...blocking.map((r) => r.x));
  const top = Math.min(...blocking.map((r) => r.y));
  const right = Math.max(...blocking.map((r) => r.x + r.width));
  const bottom = Math.max(...blocking.map((r) => r.y + r.height));

  const sourceStub = sourceSide ? offsetPoint(source, sourceSide, STUB_LENGTH) : source;
  const targetStub = targetSide ? offsetPoint(target, targetSide, STUB_LENGTH) : target;

  const dx = target.x - source.x;
  const dy = target.y - source.y;

  let corner1: Point;
  let corner2: Point;
  if (Math.abs(dx) >= Math.abs(dy)) {
    const midY = (source.y + target.y) / 2;
    const detourAboveTop = midY - top <= bottom - midY;
    const detourY = detourAboveTop
      ? top - OBSTACLE_MARGIN - extraOffset
      : bottom + OBSTACLE_MARGIN + extraOffset;
    corner1 = { x: sourceStub.x, y: detourY };
    corner2 = { x: targetStub.x, y: detourY };
  } else {
    const midX = (source.x + target.x) / 2;
    const detourLeftOfLeft = midX - left <= right - midX;
    const detourX = detourLeftOfLeft
      ? left - OBSTACLE_MARGIN - extraOffset
      : right + OBSTACLE_MARGIN + extraOffset;
    corner1 = { x: detourX, y: sourceStub.y };
    corner2 = { x: detourX, y: targetStub.y };
  }

  return [source, sourceStub, corner1, corner2, targetStub, target];
}
