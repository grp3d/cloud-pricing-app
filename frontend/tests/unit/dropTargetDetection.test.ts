import { describe, expect, it } from "vitest";

import { decideNestingChange } from "../../src/pages/dropTargetDetection";

describe("decideNestingChange", () => {
  it("nests into a VPC when dropped there and not already nested", () => {
    expect(decideNestingChange(["vpc-1"], null)).toEqual({
      changed: true,
      newParentId: "vpc-1",
    });
  });

  it("moves to a different VPC when dropped there", () => {
    expect(decideNestingChange(["vpc-2"], "vpc-1")).toEqual({
      changed: true,
      newParentId: "vpc-2",
    });
  });

  it("is a no-op when dropped back on the same VPC it's already nested in", () => {
    expect(decideNestingChange(["vpc-1"], "vpc-1")).toEqual({
      changed: false,
      newParentId: "vpc-1",
    });
  });

  it("un-nests when dropped on no VPC while previously nested", () => {
    expect(decideNestingChange([], "vpc-1")).toEqual({
      changed: true,
      newParentId: null,
    });
  });

  it("is a no-op when dropped on no VPC and wasn't nested", () => {
    expect(decideNestingChange([], null)).toEqual({
      changed: false,
      newParentId: null,
    });
  });

  it("uses the first intersecting VPC when the drop overlaps more than one", () => {
    expect(decideNestingChange(["vpc-1", "vpc-2"], null)).toEqual({
      changed: true,
      newParentId: "vpc-1",
    });
  });
});
