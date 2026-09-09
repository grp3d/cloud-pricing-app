import { describe, expect, it } from "vitest";

import { usageQuantityHint } from "../../src/lib/usageQuantityHint";

describe("usageQuantityHint", () => {
  it("is null when there's no unit yet", () => {
    expect(usageQuantityHint("on_demand", null)).toBeNull();
    expect(usageQuantityHint("on_demand", undefined)).toBeNull();
  });

  it("is per_day_estimate for an on-demand no-period unit (FR-003)", () => {
    expect(usageQuantityHint("on_demand", "Hrs")).toBe("per_day_estimate");
    expect(usageQuantityHint("on_demand", "Requests")).toBe("per_day_estimate");
  });

  it("is period_denominated for an on-demand fixed-period unit (FR-004)", () => {
    expect(usageQuantityHint("on_demand", "GB-Mo")).toBe("period_denominated");
    expect(usageQuantityHint("on_demand", "Month")).toBe("period_denominated");
  });

  it("is null for an on-demand unrecognized unit (FR-005 — excluded, no hint needed)", () => {
    expect(usageQuantityHint("on_demand", "Quantity")).toBeNull();
  });

  it("is period_denominated for any Reserved term, regardless of unit", () => {
    expect(usageQuantityHint("reserved_1yr", "Hrs")).toBe("period_denominated");
    expect(usageQuantityHint("reserved_3yr", "GB-Mo")).toBe("period_denominated");
  });
});
