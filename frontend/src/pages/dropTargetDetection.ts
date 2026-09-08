/**
 * Pure decision logic for the nest/move/un-nest drag gesture (spec FR-001-FR-003,
 * research.md #2). The actual geometry/overlap detection is React Flow's own
 * `getIntersectingNodes()` (called from `CreateArchitecturePage.tsx`'s `onNodeDragStop`) —
 * this module only decides what to do with the result, so it's testable without any DOM,
 * canvas, or React Flow instance.
 */

/**
 * Given the ids of VPC nodes the dropped Application Component node currently intersects
 * (its first entry, if any, is treated as the drop target) and the node's current parent (if
 * any), decide what nesting change — if any — should be sent to the API.
 *
 * - Intersects a VPC that isn't the current parent → nest/move to it.
 * - Intersects the VPC it's already nested in → no-op (still the same parent).
 * - Intersects no VPC but was nested → un-nest.
 * - Intersects no VPC and wasn't nested → no-op.
 */
export function decideNestingChange(
  intersectingVpcIds: string[],
  currentParentId: string | null,
): { changed: boolean; newParentId: string | null } {
  const target = intersectingVpcIds[0] ?? null;
  if (target === currentParentId) {
    return { changed: false, newParentId: currentParentId };
  }
  return { changed: true, newParentId: target };
}
