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

interface Point {
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
