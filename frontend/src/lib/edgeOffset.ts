/**
 * Parallel-Connector edge offsetting (009-ui-fixes-next-iteration, US4, FR-010, data-model.md).
 *
 * `@xyflow/react` renders multiple edges sharing the same source/target stacked exactly on top
 * of each other by default. This computes, for each edge, its index within its own
 * (order-independent) source/target pair group — 0 for the first edge in a pair, 1 for the
 * second, etc. — so `ArchitectureDiagramPanel.tsx` can apply an increasing curve offset per
 * edge, rendering parallel Connectors between the same two Collections as visually distinct,
 * independently clickable paths instead of exactly overlapping.
 *
 * Pure, no React Flow dependency, directly unit-testable — matching `nodeLayout.ts`'s
 * precedent (005-resizable-canvas-boxes).
 */

/** Order-independent key for a source/target pair — A->B and B->A share the same group, since
 * what matters for overlap is which two nodes an edge connects, not its direction. */
function pairKey(source: string, target: string): string {
  return [source, target].sort().join("::");
}

export function edgeOffsetIndex(
  edges: { id: string; source: string; target: string }[],
): Record<string, number> {
  const seen = new Map<string, number>();
  const result: Record<string, number> = {};

  for (const edge of edges) {
    const key = pairKey(edge.source, edge.target);
    const index = seen.get(key) ?? 0;
    result[edge.id] = index;
    seen.set(key, index + 1);
  }

  return result;
}
