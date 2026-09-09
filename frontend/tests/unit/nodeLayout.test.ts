import { describe, expect, it } from "vitest";

import {
  COMPONENT_BASE_HEIGHT,
  COMPONENT_ROW_HEIGHT,
  VPC_CHILD_SPACING,
  type LayoutNode,
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
