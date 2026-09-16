import { describe, expect, it } from "vitest";

import { decideNestingChange } from "../../src/pages/dropTargetDetection";

const SAME_REGION = "us-east-1";
const vpcRegions = { "vpc-1": SAME_REGION, "vpc-2": SAME_REGION };

describe("decideNestingChange", () => {
  it("nests into a VPC when dropped there and not already nested", () => {
    expect(decideNestingChange(["vpc-1"], null, SAME_REGION, vpcRegions)).toEqual({
      changed: true,
      newParentId: "vpc-1",
      rejected: false,
      rejectedVpcId: null,
    });
  });

  it("moves to a different VPC when dropped there", () => {
    expect(decideNestingChange(["vpc-2"], "vpc-1", SAME_REGION, vpcRegions)).toEqual({
      changed: true,
      newParentId: "vpc-2",
      rejected: false,
      rejectedVpcId: null,
    });
  });

  it("is a no-op when dropped back on the same VPC it's already nested in", () => {
    expect(decideNestingChange(["vpc-1"], "vpc-1", SAME_REGION, vpcRegions)).toEqual({
      changed: false,
      newParentId: "vpc-1",
      rejected: false,
      rejectedVpcId: null,
    });
  });

  it("un-nests when dropped on no VPC while previously nested", () => {
    expect(decideNestingChange([], "vpc-1", SAME_REGION, vpcRegions)).toEqual({
      changed: true,
      newParentId: null,
      rejected: false,
      rejectedVpcId: null,
    });
  });

  it("is a no-op when dropped on no VPC and wasn't nested", () => {
    expect(decideNestingChange([], null, SAME_REGION, vpcRegions)).toEqual({
      changed: false,
      newParentId: null,
      rejected: false,
      rejectedVpcId: null,
    });
  });

  it("uses the first intersecting VPC when the drop overlaps more than one", () => {
    expect(decideNestingChange(["vpc-1", "vpc-2"], null, SAME_REGION, vpcRegions)).toEqual({
      changed: true,
      newParentId: "vpc-1",
      rejected: false,
      rejectedVpcId: null,
    });
  });

  // --- 010-multi-region-support, spec FR-004: same-region nesting only ---

  it("rejects nesting into a VPC in a different region", () => {
    const regions = { "vpc-1": "eu-west-1" };
    expect(decideNestingChange(["vpc-1"], null, "us-east-1", regions)).toEqual({
      changed: false,
      newParentId: null,
      rejected: true,
      rejectedVpcId: "vpc-1",
    });
  });

  it("rejects moving to a different-region VPC, leaving the current parent unchanged", () => {
    const regions = { "vpc-1": "us-east-1", "vpc-2": "eu-west-1" };
    expect(decideNestingChange(["vpc-2"], "vpc-1", "us-east-1", regions)).toEqual({
      changed: false,
      newParentId: "vpc-1",
      rejected: true,
      rejectedVpcId: "vpc-2",
    });
  });

  it("does not consult regions at all for an un-nest (no target VPC)", () => {
    // Deliberately empty vpcRegions — must not throw or reject when there's no target to check.
    expect(decideNestingChange([], "vpc-1", "us-east-1", {})).toEqual({
      changed: true,
      newParentId: null,
      rejected: false,
      rejectedVpcId: null,
    });
  });
});
