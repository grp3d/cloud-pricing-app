import { describe, expect, it } from "vitest";

import { decideBaselineUpdate, type PriceChangeSelection, type PriorCalculation } from "../../src/lib/priceChange";

function selection(overrides: Partial<PriceChangeSelection> = {}): PriceChangeSelection {
  return {
    service_code: "AmazonEC2",
    sku: "SKU1",
    pricing_term: "on_demand",
    purchase_option: "not_applicable",
    usage_quantity: "1",
    ...overrides,
  };
}

function prior(overrides: Partial<PriorCalculation> = {}): PriorCalculation {
  return {
    total: "10.00",
    duration: "1_month",
    selections: [selection()],
    ...overrides,
  };
}

describe("decideBaselineUpdate", () => {
  it("establishes a first baseline when none exists yet (no Price Change to show)", () => {
    const decision = decideBaselineUpdate({
      prior: null,
      currentSelections: [selection()],
      newDuration: "1_month",
    });
    expect(decision).toBe("establish");
  });

  it("leaves the baseline unchanged on a true no-op Calculate (FR-016)", () => {
    const decision = decideBaselineUpdate({
      prior: prior(),
      currentSelections: [selection()],
      newDuration: "1_month",
    });
    expect(decision).toBe("unchanged");
  });

  it("flags a duration-only adjustment when only the Duration selection changed (009, FR-002/003 — supersedes 008's FR-016, which wrongly left this case as \"unchanged\")", () => {
    const decision = decideBaselineUpdate({
      prior: prior({ duration: "1_month" }),
      currentSelections: [selection()], // identical content
      newDuration: "1_year", // duration alone differs
    });
    expect(decision).toBe("duration_only");
  });

  it("flags duration-only a second time when switching back to the original duration, since the baseline's duration already advanced on the first switch (009, FR-004, data-model.md's correction)", () => {
    // Simulates the caller's two-step flow: first switch (1_month -> 1_year) advances the
    // stored baseline's duration to 1_year; switching back (1_year -> 1_month) compares
    // against that already-advanced baseline, so it's "duration_only" again, not "unchanged".
    const decision = decideBaselineUpdate({
      prior: prior({ duration: "1_year" }), // baseline already advanced by the first switch
      currentSelections: [selection()], // still identical content
      newDuration: "1_month", // switching back
    });
    expect(decision).toBe("duration_only");
  });

  it("treats reordered-but-identical selections as unchanged (multiset, not positional)", () => {
    const a = selection({ sku: "SKU1" });
    const b = selection({ sku: "SKU2", service_code: "AmazonS3" });
    const decision = decideBaselineUpdate({
      prior: prior({ selections: [a, b] }),
      currentSelections: [b, a], // same two selections, reversed order
      newDuration: "1_month",
    });
    expect(decision).toBe("unchanged");
  });

  it("flags a direct comparison when content changed but Duration did not (FR-015/016)", () => {
    const decision = decideBaselineUpdate({
      prior: prior({ duration: "1_month", selections: [selection({ sku: "SKU1" })] }),
      currentSelections: [selection({ sku: "SKU1" }), selection({ sku: "SKU2" })], // added a SKU
      newDuration: "1_month",
    });
    expect(decision).toBe("direct");
  });

  it("detects an edited selection (same sku, different pricing input) as a content change", () => {
    const decision = decideBaselineUpdate({
      prior: prior({ selections: [selection({ usage_quantity: "1" })] }),
      currentSelections: [selection({ usage_quantity: "2" })],
      newDuration: "1_month",
    });
    expect(decision).toBe("direct");
  });

  it("detects a removed selection as a content change", () => {
    const decision = decideBaselineUpdate({
      prior: prior({ selections: [selection({ sku: "SKU1" }), selection({ sku: "SKU2" })] }),
      currentSelections: [selection({ sku: "SKU1" })],
      newDuration: "1_month",
    });
    expect(decision).toBe("direct");
  });

  it("flags the duration-adjusted snapshot path when content AND Duration both changed (FR-016a)", () => {
    const decision = decideBaselineUpdate({
      prior: prior({ duration: "1_month", selections: [selection({ sku: "SKU1" })] }),
      currentSelections: [selection({ sku: "SKU1" }), selection({ sku: "SKU2" })],
      newDuration: "1_year",
    });
    expect(decision).toBe("duration_adjusted");
  });
});
