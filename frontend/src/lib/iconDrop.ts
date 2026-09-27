/**
 * What dropping a service icon at a canvas point means (016-canvas-icon-layout, FR-004–FR-004b,
 * research.md §8). Pure — boxes and the point are plain flow-space rects — so the rules are
 * test-first (Constitution Principle V): the box under the point wins by depth (a nested
 * Application beats the VPC around it); the icon's own box is a reposition; another box in the
 * same region is a move of the service; another region is refused; empty canvas is a no-op.
 * The backend re-checks every move (`PATCH /sku-selections/{id}`); this only decides what to
 * ask for, and what to tell the user without a round trip.
 */

export interface DropBox {
  id: string;
  parentId?: string;
  region: string;
  /** Absolute flow-space rect of the box. */
  rect: { x: number; y: number; width: number; height: number };
}

export type IconDropDecision =
  | { kind: "none" }
  | { kind: "reject-region"; sourceRegion: string }
  | { kind: "same-box"; targetId: string }
  | { kind: "move"; targetId: string };

function depthOf(box: DropBox, byId: Map<string, DropBox>): number {
  let depth = 0;
  let parentId = box.parentId;
  while (parentId) {
    depth++;
    parentId = byId.get(parentId)?.parentId;
  }
  return depth;
}

export function decideIconDrop(params: {
  point: { x: number; y: number };
  boxes: DropBox[];
  sourceId: string;
}): IconDropDecision {
  const { point, boxes, sourceId } = params;
  const byId = new Map(boxes.map((b) => [b.id, b]));
  const source = byId.get(sourceId);
  if (!source) return { kind: "none" };

  const target = boxes
    .filter(
      ({ rect }) =>
        point.x >= rect.x &&
        point.x <= rect.x + rect.width &&
        point.y >= rect.y &&
        point.y <= rect.y + rect.height,
    )
    .sort((a, b) => depthOf(b, byId) - depthOf(a, byId))[0];

  if (!target) return { kind: "none" };
  if (target.id === source.id) return { kind: "same-box", targetId: target.id };
  if (target.region !== source.region)
    return { kind: "reject-region", sourceRegion: source.region };
  return { kind: "move", targetId: target.id };
}
