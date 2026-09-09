import { describe, expect, it } from "vitest";

import { summarizeAttributes } from "../../src/lib/skuDetail";

describe("summarizeAttributes", () => {
  it("joins present candidate keys with a middle dot, in candidate-list order", () => {
    // DETAIL_CANDIDATE_KEYS orders memory before vcpu, regardless of input key order.
    expect(
      summarizeAttributes({ instanceType: "t3.medium", vcpu: "2", memory: "4 GiB" }),
    ).toBe("t3.medium · 4 GiB · 2");
  });

  it("skips candidate keys that aren't present", () => {
    expect(summarizeAttributes({ instanceType: "t3.medium" })).toBe("t3.medium");
  });

  it("ignores non-candidate keys entirely", () => {
    expect(summarizeAttributes({ servicecode: "AmazonEC2", location: "US East" })).toBe("");
  });

  it("returns an empty string for an empty attributes map", () => {
    expect(summarizeAttributes({})).toBe("");
  });
});
