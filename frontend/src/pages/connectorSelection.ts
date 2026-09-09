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
