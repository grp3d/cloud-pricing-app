import { describe, expect, it } from "vitest";

import {
  COMPONENT_BASE_HEIGHT,
  COMPONENT_ROW_HEIGHT,
  VPC_CHILD_SPACING,
  type LayoutNode,
  type MeasuredLayoutNode,
  childYOffsets,
  computeMeasuredHeight,
  estimateComponentHeight,
  estimateNodeHeight,
} from "../../src/pages/nodeLayout";

describe("estimateComponentHeight", () => {
  it("gives a zero-service component one row's worth of height, not a near-empty box", () => {
    expect(estimateComponentHeight(0)).toBe(COMPONENT_BASE_HEIGHT + COMPONENT_ROW_HEIGHT);
  });

  it("grows linearly with the number of services", () => {
    expect(estimateComponentHeight(3)).toBe(COMPONENT_BASE_HEIGHT + 3 * COMPONENT_ROW_HEIGHT);
  });

  it("grows for a single service the same way", () => {
    expect(estimateComponentHeight(1)).toBe(COMPONENT_BASE_HEIGHT + COMPONENT_ROW_HEIGHT);
  });
});

function leaf(ownServiceCount: number): LayoutNode {
  return { ownServiceCount, children: [] };
}

describe("estimateNodeHeight", () => {
  it("reduces to estimateComponentHeight for a leaf node (no children)", () => {
    expect(estimateNodeHeight(leaf(3))).toBe(estimateComponentHeight(3));
  });

  it("gives an empty container (no own services, no children) one row's worth of height", () => {
    expect(estimateNodeHeight(leaf(0))).toBe(estimateComponentHeight(0));
  });

  it("sums one child's height plus the container's own content and spacing", () => {
    const node: LayoutNode = { ownServiceCount: 0, children: [leaf(2)] };
    expect(estimateNodeHeight(node)).toBe(
      estimateComponentHeight(0) + estimateComponentHeight(2) + VPC_CHILD_SPACING,
    );
  });

  it("sums multiple children's heights, each with its own spacing", () => {
    const node: LayoutNode = { ownServiceCount: 0, children: [leaf(1), leaf(3)] };
    expect(estimateNodeHeight(node)).toBe(
      estimateComponentHeight(0) +
        estimateComponentHeight(1) +
        VPC_CHILD_SPACING +
        estimateComponentHeight(3) +
        VPC_CHILD_SPACING,
    );
  });

  it("includes a container's own directly-attached services alongside its children's (004, FR-015)", () => {
    const withOwnServices: LayoutNode = { ownServiceCount: 2, children: [leaf(1)] };
    const withoutOwnServices: LayoutNode = { ownServiceCount: 0, children: [leaf(1)] };
    expect(estimateNodeHeight(withOwnServices)).toBeGreaterThan(
      estimateNodeHeight(withoutOwnServices),
    );
  });

  it("reflects variable-height children rather than a fixed per-child amount", () => {
    const uniform = estimateNodeHeight({ ownServiceCount: 0, children: [leaf(1), leaf(1)] });
    const variable = estimateNodeHeight({ ownServiceCount: 0, children: [leaf(1), leaf(5)] });
    expect(variable).toBeGreaterThan(uniform);
  });

  it("cascades growth up through multiple levels of nesting (004, FR-016)", () => {
    const shallow: LayoutNode = { ownServiceCount: 0, children: [leaf(1)] };
    const deep: LayoutNode = {
      ownServiceCount: 0,
      children: [{ ownServiceCount: 0, children: [leaf(1), leaf(1)] }],
    };
    // The deeply-nested grandchild content makes the whole ancestor chain taller, not just the
    // immediate child.
    expect(estimateNodeHeight(deep)).toBeGreaterThan(estimateNodeHeight(shallow));
  });
});

function measuredLeaf(id: string, ownServiceCount: number): MeasuredLayoutNode {
  return { id, ownServiceCount, children: [] };
}

describe("computeMeasuredHeight (005: real measurement, not an estimate)", () => {
  it("uses a real measured own-height when one is available, instead of the estimate", () => {
    expect(computeMeasuredHeight(measuredLeaf("a", 2), { a: 999 })).toBe(999);
  });

  it("falls back to the estimate for a node with no measurement yet (first-paint placeholder)", () => {
    expect(computeMeasuredHeight(measuredLeaf("a", 2), {})).toBe(estimateComponentHeight(2));
  });

  it("sums a real measured child height plus the container's own measured height and spacing", () => {
    const node: MeasuredLayoutNode = {
      id: "parent",
      ownServiceCount: 0,
      children: [measuredLeaf("child", 1)],
    };
    expect(computeMeasuredHeight(node, { parent: 50, child: 200 })).toBe(
      50 + 200 + VPC_CHILD_SPACING,
    );
  });

  it("mixes a real measured height with an estimated fallback within the same tree", () => {
    const node: MeasuredLayoutNode = {
      id: "parent",
      ownServiceCount: 0,
      children: [measuredLeaf("child", 3)],
    };
    // Only the parent has a real measurement here; the child falls back to its estimate.
    expect(computeMeasuredHeight(node, { parent: 40 })).toBe(
      40 + estimateComponentHeight(3) + VPC_CHILD_SPACING,
    );
  });

  it("cascades a real measured grandchild height up through multiple levels of nesting", () => {
    const deep: MeasuredLayoutNode = {
      id: "root",
      ownServiceCount: 0,
      children: [{ id: "mid", ownServiceCount: 0, children: [measuredLeaf("leaf", 1)] }],
    };
    const tall = computeMeasuredHeight(deep, { leaf: 500 });
    const short = computeMeasuredHeight(deep, { leaf: 10 });
    expect(tall).toBeGreaterThan(short);
  });
});

describe("childYOffsets (005)", () => {
  it("offsets the first child by the parent's own measured height", () => {
    const node: MeasuredLayoutNode = {
      id: "parent",
      ownServiceCount: 0,
      children: [measuredLeaf("child", 1)],
    };
    expect(childYOffsets(node, { parent: 70 })).toEqual({ child: 70 });
  });

  it("stacks a second child below the first child's own real measured height plus spacing", () => {
    const node: MeasuredLayoutNode = {
      id: "parent",
      ownServiceCount: 0,
      children: [measuredLeaf("a", 1), measuredLeaf("b", 1)],
    };
    const offsets = childYOffsets(node, { parent: 60, a: 300 });
    expect(offsets.a).toBe(60);
    expect(offsets.b).toBe(60 + 300 + VPC_CHILD_SPACING);
  });

  it("falls back to the estimate for offsets when no measurement is available yet", () => {
    const node: MeasuredLayoutNode = {
      id: "parent",
      ownServiceCount: 2,
      children: [measuredLeaf("child", 1)],
    };
    expect(childYOffsets(node, {})).toEqual({ child: estimateComponentHeight(2) });
  });
});
