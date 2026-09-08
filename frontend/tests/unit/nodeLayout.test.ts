import { describe, expect, it } from "vitest";

import {
  COMPONENT_BASE_HEIGHT,
  COMPONENT_ROW_HEIGHT,
  VPC_HEADER_HEIGHT,
  VPC_CHILD_SPACING,
  VPC_MIN_HEIGHT,
  estimateComponentHeight,
  estimateVpcHeight,
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

describe("estimateVpcHeight", () => {
  it("falls back to the fixed minimum for an empty VPC", () => {
    expect(estimateVpcHeight([])).toBe(VPC_MIN_HEIGHT);
  });

  it("sums one child's height plus header and spacing", () => {
    expect(estimateVpcHeight([100])).toBe(VPC_HEADER_HEIGHT + 100 + VPC_CHILD_SPACING);
  });

  it("sums multiple children's heights, each with its own spacing", () => {
    expect(estimateVpcHeight([100, 150])).toBe(
      VPC_HEADER_HEIGHT + 100 + VPC_CHILD_SPACING + 150 + VPC_CHILD_SPACING,
    );
  });

  it("reflects variable-height children rather than a fixed per-child amount", () => {
    const uniform = estimateVpcHeight([estimateComponentHeight(1), estimateComponentHeight(1)]);
    const variable = estimateVpcHeight([estimateComponentHeight(1), estimateComponentHeight(5)]);
    expect(variable).toBeGreaterThan(uniform);
  });
});
