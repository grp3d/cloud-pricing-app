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
 * - Intersects a VPC that isn't the current parent, same region → nest/move to it.
 * - Intersects a VPC that isn't the current parent, different region → rejected
 *   (010-multi-region-support, spec FR-004) — no change, `rejected: true`.
 * - Intersects the VPC it's already nested in → no-op (still the same parent).
 * - Intersects no VPC but was nested → un-nest.
 * - Intersects no VPC and wasn't nested → no-op.
 *
 * `applicationRegion` and `vpcRegions` (keyed by VPC id) are only consulted when a nest/move
 * is otherwise about to happen — an un-nest or no-op never needs them.
 */
export function decideNestingChange(
  intersectingVpcIds: string[],
  currentParentId: string | null,
  applicationRegion: string,
  vpcRegions: Record<string, string>,
): { changed: boolean; newParentId: string | null; rejected: boolean; rejectedVpcId: string | null } {
  const target = intersectingVpcIds[0] ?? null;
  if (target === currentParentId) {
    return { changed: false, newParentId: currentParentId, rejected: false, rejectedVpcId: null };
  }
  if (target !== null && vpcRegions[target] !== applicationRegion) {
    return { changed: false, newParentId: currentParentId, rejected: true, rejectedVpcId: target };
  }
  return { changed: true, newParentId: target, rejected: false, rejectedVpcId: null };
}
