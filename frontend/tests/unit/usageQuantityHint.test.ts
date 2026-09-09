import { describe, expect, it } from "vitest";

import { usageQuantityHint } from "../../src/lib/usageQuantityHint";

describe("usageQuantityHint", () => {
  it("is null when there's no unit yet", () => {
    expect(usageQuantityHint(null)).toBeNull();
    expect(usageQuantityHint(undefined)).toBeNull();
  });

  it("is per_day_estimate for a no-period unit (FR-003)", () => {
    expect(usageQuantityHint("Hrs")).toBe("per_day_estimate");
    expect(usageQuantityHint("Requests")).toBe("per_day_estimate");
  });

  it("is period_denominated for a fixed-period unit (FR-004)", () => {
    expect(usageQuantityHint("GB-Mo")).toBe("period_denominated");
    expect(usageQuantityHint("Month")).toBe("period_denominated");
  });

  it("is null for an unrecognized unit (FR-005 — excluded, no hint needed)", () => {
    expect(usageQuantityHint("Quantity")).toBeNull();
  });

  // 006-fix-reserved-pricing: the Reserved-term case (previously `usageQuantityHint(term,
  // unit)` returning "period_denominated" for any Reserved term) is gone — the usage-quantity
  // input isn't shown at all for a Reserved term (PricingInputsForm.test.tsx), so there's no
  // hint left to compute for that case, and the `term` parameter is gone with it.
});
