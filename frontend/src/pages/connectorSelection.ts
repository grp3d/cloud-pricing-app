/**
 * Pure decision logic for the "Connect" action's enabled state
 * (004-canvas-pricing-improvements, FR-008, FR-009). The selection itself comes from React
 * Flow's own built-in multi-select (research.md #7); this module only decides what to do with
 * the resulting id list, so it's testable without any DOM, canvas, or React Flow instance —
 * matching the `dropTargetDetection.ts`/`nodeLayout.ts` precedent from `002`/`003`.
 */

/** The "Connect" action is enabled only when exactly two boxes are currently selected
 * (FR-008, FR-009) — zero, one, or three-or-more all disable it. */
export function canConnect(selectedNodeIds: string[]): boolean {
  return selectedNodeIds.length === 2;
}

/**
 * 010-multi-region-support, spec FR-008: when a Connector is created by selecting two boxes
 * in column 2 (rather than the explicit "Add Connector" dialog), the first-*selected* box is
 * "from" and the second-*selected* is "to". React Flow's own `useOnSelectionChange` reports
 * the selected set in its internal node-array order, not click order, so click order has to be
 * tracked separately: given the previous click-ordered list and the *current* full selected-id
 * set (whatever order React Flow reports it in), keep every still-selected id in its previous
 * relative order and append any newly-selected id(s) at the end.
 */
export function updateOrderedSelection(previousOrder: string[], currentIds: string[]): string[] {
  const currentSet = new Set(currentIds);
  const preserved = previousOrder.filter((id) => currentSet.has(id));
  const preservedSet = new Set(preserved);
  const newlyAdded = currentIds.filter((id) => !preservedSet.has(id));
  return [...preserved, ...newlyAdded];
}
