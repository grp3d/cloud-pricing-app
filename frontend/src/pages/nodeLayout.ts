/**
 * Pure functions estimating canvas node height from content (spec FR-007, FR-011,
 * research.md #4). React Flow's parent/child nodes are independently positioned graph nodes,
 * not DOM children of their parent's own render, so a parent's size must be computed ahead of
 * render rather than left to organic CSS auto-sizing — these are *estimates*, not measured
 * rendered pixel heights (research.md #4's deliberate simplicity choice), extracted with no
 * DOM/React Flow dependency so they're directly unit-testable, matching the
 * `dropTargetDetection.ts` precedent from 002-vpc-component-nesting.
 */

/** An Application Component's box grows with its SKU Selection count. A component with zero
 * services still gets one row's worth of height (never a near-invisible empty box). */
export const COMPONENT_BASE_HEIGHT = 60;
export const COMPONENT_ROW_HEIGHT = 24;

/** A VPC's own header/label area, plus spacing added below each nested child. */
export const VPC_HEADER_HEIGHT = 50;
export const VPC_CHILD_SPACING = 10;
/** An empty VPC (no nested children) falls back to this fixed minimum. */
export const VPC_MIN_HEIGHT = 80;

/** Estimated height for an Application Component node, given how many SKU Selections it has. */
export function estimateComponentHeight(skuCount: number): number {
  return COMPONENT_BASE_HEIGHT + Math.max(1, skuCount) * COMPONENT_ROW_HEIGHT;
}

/** Estimated height for a VPC node, given its nested children's own estimated heights
 * (typically each computed via `estimateComponentHeight`) — replaces 002's original fixed
 * 50px-per-child assumption with a height that actually reflects each child's content. */
export function estimateVpcHeight(childHeights: number[]): number {
  if (childHeights.length === 0) return VPC_MIN_HEIGHT;
  const childrenTotal = childHeights.reduce((sum, height) => sum + height + VPC_CHILD_SPACING, 0);
  return VPC_HEADER_HEIGHT + childrenTotal;
}
