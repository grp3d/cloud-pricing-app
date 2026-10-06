import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CalculationResult } from "../../src/api/client";
import {
  applyCalculationSuccess,
  readPricingResult,
  removePricingResult,
  shouldAutoCalculate,
  writePricingResult,
  type CalculationRequestVars,
  type PricingResultEntry,
} from "../../src/lib/architecturePricingResults";
import type { PriceChangeSelection, PricedContentsEntry } from "../../src/lib/priceChange";

const selection: PriceChangeSelection = {
  service_code: "AmazonEC2",
  sku: "SKU1",
  pricing_term: "on_demand",
  purchase_option: "not_applicable",
  usage_quantity: "730",
};
const priced: PricedContentsEntry = { ...selection, region: "us-east-1" };

function result(total: string): CalculationResult {
  return {
    snapshot_date: "2026-09-24",
    snapshot_revision: 1,
    duration: "1_month",
    total_price: total,
    currency: "USD",
    line_items: [],
    unpriceable: [],
    warnings: [],
  };
}

function entry(overrides: Partial<PricingResultEntry> = {}): PricingResultEntry {
  return {
    version: 1,
    result: result("10.00"),
    duration: "1_month",
    priceChange: null,
    pricedContents: [priced],
    calculatedAt: "2026-09-25T00:00:00.000Z",
    ...overrides,
  };
}

function vars(overrides: Partial<CalculationRequestVars> = {}): CalculationRequestVars {
  return {
    architectureId: "A",
    duration: "1_month",
    pricedContents: [priced],
    priceChangeSelections: [selection],
    prior: null,
    ...overrides,
  };
}

describe("pricing result storage", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("round-trips an entry under cloud-pricing-result-<id>", () => {
    writePricingResult("A", entry());
    expect(localStorage.getItem("cloud-pricing-result-A")).not.toBeNull();
    expect(readPricingResult("A")).toEqual(entry());
  });

  it("keeps each architecture's entry independent", () => {
    writePricingResult("A", entry());
    writePricingResult("B", entry({ result: result("99.00") }));
    expect(readPricingResult("A")?.result.total_price).toBe("10.00");
    expect(readPricingResult("B")?.result.total_price).toBe("99.00");
  });

  it("reads a missing, malformed, or wrong-shape entry as null", () => {
    expect(readPricingResult("missing")).toBeNull();
    localStorage.setItem("cloud-pricing-result-bad", "{not json");
    expect(readPricingResult("bad")).toBeNull();
    localStorage.setItem("cloud-pricing-result-v2", JSON.stringify({ ...entry(), version: 2 }));
    expect(readPricingResult("v2")).toBeNull();
    localStorage.setItem(
      "cloud-pricing-result-noresult",
      JSON.stringify({ ...entry(), result: undefined }),
    );
    expect(readPricingResult("noresult")).toBeNull();
    localStorage.setItem(
      "cloud-pricing-result-nocontents",
      JSON.stringify({ ...entry(), pricedContents: undefined }),
    );
    expect(readPricingResult("nocontents")).toBeNull();
  });

  it("removes only the given architecture's entry", () => {
    writePricingResult("A", entry());
    writePricingResult("B", entry());
    removePricingResult("A");
    expect(readPricingResult("A")).toBeNull();
    expect(readPricingResult("B")).not.toBeNull();
  });

  it("never throws when storage itself throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readPricingResult("A")).toBeNull();
    expect(() => writePricingResult("A", entry())).not.toThrow();
    expect(() => removePricingResult("A")).not.toThrow();
  });
});

describe("shouldAutoCalculate", () => {
  const base = {
    architectureId: "A",
    hasSelections: true,
    hasStoredEntry: false,
    isInFlight: false,
    hasError: false,
  };

  it("fires for an architecture with services, no stored result, and nothing in flight", () => {
    expect(shouldAutoCalculate(base)).toBe(true);
  });

  it.each([
    ["no architecture", { architectureId: undefined }],
    ["no services", { hasSelections: false }],
    ["a stored result", { hasStoredEntry: true }],
    ["a request in flight", { isInFlight: true }],
    ["a failed attempt showing (Retry is the user's call, not a loop)", { hasError: true }],
  ])("does not fire with %s", (_label, overrides) => {
    expect(shouldAutoCalculate({ ...base, ...overrides })).toBe(false);
  });
});

describe("applyCalculationSuccess", () => {
  const now = "2026-09-25T12:00:00.000Z";

  it("changes only the requested architecture's entry, even if another is active (FR-020)", () => {
    const entries = new Map([["B", entry({ result: result("99.00") })]]);
    const out = applyCalculationSuccess({
      entries,
      vars: vars({ architectureId: "A" }),
      result: result("12.00"),
      decision: "establish",
      comparisonTotal: null,
      previousEntry: undefined,
      now,
    });
    expect(out.entries.get("A")?.result.total_price).toBe("12.00");
    expect(out.entries.get("B")).toBe(entries.get("B"));
    expect(entries.has("A")).toBe(false); // input map is not mutated
  });

  it("establishes a first baseline with no Price Change", () => {
    const out = applyCalculationSuccess({
      entries: new Map(),
      vars: vars(),
      result: result("12.00"),
      decision: "establish",
      comparisonTotal: null,
      previousEntry: undefined,
      now,
    });
    expect(out.entry.priceChange).toBeNull();
    expect(out.newBaseline).toEqual({
      total: "12.00",
      duration: "1_month",
      selections: [selection],
    });
  });

  it.each(["direct", "duration_adjusted", "duration_only"] as const)(
    "computes Price Change against the comparison total for %s",
    (decision) => {
      const out = applyCalculationSuccess({
        entries: new Map(),
        vars: vars(),
        result: result("15.5"),
        decision,
        comparisonTotal: "10",
        previousEntry: undefined,
        now,
      });
      expect(out.entry.priceChange).toBe("5.5");
      expect(out.newBaseline?.total).toBe("15.5");
    },
  );

  it("carries the previous Price Change forward and leaves the baseline alone when unchanged (FR-022)", () => {
    const out = applyCalculationSuccess({
      entries: new Map(),
      vars: vars(),
      result: result("10.00"),
      decision: "unchanged",
      comparisonTotal: null,
      previousEntry: entry({ priceChange: "-3" }),
      now,
    });
    expect(out.entry.priceChange).toBe("-3");
    expect(out.newBaseline).toBeNull();
  });

  it("uses null Price Change when unchanged with no previous entry", () => {
    const out = applyCalculationSuccess({
      entries: new Map(),
      vars: vars(),
      result: result("10.00"),
      decision: "unchanged",
      comparisonTotal: null,
      previousEntry: undefined,
      now,
    });
    expect(out.entry.priceChange).toBeNull();
  });

  it("records duration and priced contents from the request, not current state (FR-020)", () => {
    const requested = [{ ...priced, usage_quantity: "1" }];
    const out = applyCalculationSuccess({
      entries: new Map(),
      vars: vars({ duration: "1_year", pricedContents: requested }),
      result: result("1.00"),
      decision: "establish",
      comparisonTotal: null,
      previousEntry: undefined,
      now,
    });
    expect(out.entry.duration).toBe("1_year");
    expect(out.entry.pricedContents).toEqual(requested);
    expect(out.entry.calculatedAt).toBe(now);
    expect(out.entry.version).toBe(1);
  });
});
