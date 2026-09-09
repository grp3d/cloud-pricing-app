/**
 * Pure functions computing canvas node height from content (spec FR-007, FR-011;
 * 004-canvas-pricing-improvements FR-015, FR-016, FR-017; 005-resizable-canvas-boxes FR-003,
 * FR-004, FR-005). React Flow's parent/child nodes are independently positioned graph nodes, not
 * DOM children of their parent's own render, so a parent's size must be computed ahead of render
 * rather than left to organic CSS auto-sizing.
 *
 * `estimateComponentHeight`/`estimateNodeHeight` are a character/service-count *estimate*
 * (004's/003's original, deliberately simple, choice — research.md #4). `computeMeasuredHeight`/
 * `childYOffsets` (005) supersede them as the authority on avoiding clipped text, sourcing each
 * node's own-content height from a real `ResizeObserver` measurement where one exists
 * (005/research.md #2) and falling back to the estimate only for a node's very first render,
 * before its first real measurement has landed.
 *
 * All of it is extracted with no DOM/React Flow dependency so it's directly unit-testable,
 * matching the `dropTargetDetection.ts` precedent from 002-vpc-component-nesting.
 */

/** A box grows with its own directly-attached SKU Selection count — an Application Component's,
 * or (004, FR-015) a VPC's own directly-attached services. A box with zero services still gets
 * one row's worth of height (never a near-invisible empty box). */
export const COMPONENT_BASE_HEIGHT = 60;
export const COMPONENT_ROW_HEIGHT = 24;

/** Spacing added below each nested child when summing a container's height. */
export const VPC_CHILD_SPACING = 10;

/** Estimated height for a leaf box (no nested children), given how many of its own SKU
 * Selections it has. Also used, via `estimateNodeHeight`, as the "own content" contribution for
 * a container box that also has nested children. */
export function estimateComponentHeight(skuCount: number): number {
  return COMPONENT_BASE_HEIGHT + Math.max(1, skuCount) * COMPONENT_ROW_HEIGHT;
}

/** One node in the canvas nesting tree, as far as height estimation needs to know about it. */
export interface LayoutNode {
  /** Count of this node's own directly-attached SKU Selections. */
  ownServiceCount: number;
  /** Nested children, each already expressed the same way — however many levels deep. */
  children: LayoutNode[];
}

/**
 * Estimated height for one node in the nesting tree — its own content's height
 * (`estimateComponentHeight` of its own service count) plus the sum of its children's own
 * (already-recursively-computed) heights, each with spacing (004, FR-015/FR-016/FR-017).
 *
 * A leaf node (no children) reduces to exactly `estimateComponentHeight`'s formula — this
 * replaces 002's/003's one-level-only `estimateVpcHeight`, which only ever summed a VPC's
 * *direct* children and never accounted for a VPC's own services: growth at any depth now
 * cascades all the way up through however many levels of nesting exist (research.md #6), and an
 * empty container (no own services, no children) still gets one row's worth of height via the
 * same `estimateComponentHeight(0)` floor a leaf box gets — no separate empty-VPC constant
 * needed.
 */
export function estimateNodeHeight(node: LayoutNode): number {
  const ownHeight = estimateComponentHeight(node.ownServiceCount);
  const childrenTotal = node.children.reduce(
    (sum, child) => sum + estimateNodeHeight(child) + VPC_CHILD_SPACING,
    0,
  );
  return ownHeight + childrenTotal;
}

/**
 * A `LayoutNode` plus a stable id (005-resizable-canvas-boxes) — the id lets
 * `computeMeasuredHeight`/`childYOffsets` below look up a node's real, browser-*measured* "own
 * content" height, when one is available, instead of the `ownServiceCount`-based estimate above.
 * `estimateComponentHeight`/`estimateNodeHeight` are no longer the authority on avoiding clipped
 * text (research.md #2) — they're kept unchanged as the fallback for a node's very first render,
 * before its first real measurement has landed (avoiding a 0-height flash), which is exactly what
 * the `?? estimateComponentHeight(...)` fallback below does.
 */
export interface MeasuredLayoutNode extends LayoutNode {
  id: string;
  children: MeasuredLayoutNode[];
}

/**
 * Same recursive shape as `estimateNodeHeight`, but sourcing each node's own-content height from
 * a real measurement (`ownHeights`, keyed by node id) where one exists, falling back to the
 * estimate otherwise. This is what makes a box's real, guaranteed-non-clipping content height
 * cascade up through however many levels of nesting exist (FR-003, FR-004, FR-005).
 */
export function computeMeasuredHeight(
  node: MeasuredLayoutNode,
  ownHeights: Record<string, number>,
): number {
  const ownHeight = ownHeights[node.id] ?? estimateComponentHeight(node.ownServiceCount);
  const childrenTotal = node.children.reduce(
    (sum, child) => sum + computeMeasuredHeight(child, ownHeights) + VPC_CHILD_SPACING,
    0,
  );
  return ownHeight + childrenTotal;
}

/**
 * Y-offset of each of `node`'s direct children within its own box — the same stacking rule
 * `computeMeasuredHeight` sums, exposed per-child so a container's children can be positioned
 * below its own (measured or estimated) content instead of a fixed offset (FR-005).
 */
export function childYOffsets(
  node: MeasuredLayoutNode,
  ownHeights: Record<string, number>,
): Record<string, number> {
  const offsets: Record<string, number> = {};
  let y = ownHeights[node.id] ?? estimateComponentHeight(node.ownServiceCount);
  for (const child of node.children) {
    offsets[child.id] = y;
    y += computeMeasuredHeight(child, ownHeights) + VPC_CHILD_SPACING;
  }
  return offsets;
}
