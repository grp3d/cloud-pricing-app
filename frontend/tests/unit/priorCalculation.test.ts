import { beforeEach, describe, expect, it } from "vitest";

import type { PriorCalculation } from "../../src/lib/priceChange";
import { readPriorCalculation, writePriorCalculation } from "../../src/lib/priorCalculation";

// 020 (T009, data-model §3): version 2 and legacy baselines both read back; anything
// unreadable reads as "no baseline yet".

const KEY = "cloud-pricing-prior-calculation-A";

const legacy: PriorCalculation = {
  total: "10",
  duration: "1_month",
  selections: [
    {
      service_code: "AmazonEC2",
      sku: "SKU1",
      pricing_term: "on_demand",
      purchase_option: "not_applicable",
      usage_quantity: "24",
    },
  ],
};

const v2: PriorCalculation = {
  version: 2,
  total: "10",
  duration: "1_month",
  selections: [
    {
      service_code: "6F81-5844-456A",
      sku: "CORE",
      pricing_term: "on_demand",
      purchase_option: "not_applicable",
      usage_quantity: "24",
      region: "us-east1",
      provider_options: {
        kind: "gcp_machine",
        version: 1,
        vcpus: 4,
        memory_gib: "16",
        ram_sku: "RAM",
      },
    },
    {
      service_code: "6F81-5844-456A",
      sku: "DISK",
      pricing_term: "on_demand",
      purchase_option: "not_applicable",
      usage_quantity: "100",
      region: null,
      provider_options: null,
    },
  ],
};

describe("readPriorCalculation", () => {
  beforeEach(() => localStorage.clear());

  it("round-trips a version 2 baseline", () => {
    writePriorCalculation("A", v2);
    expect(readPriorCalculation("A")).toEqual(v2);
  });

  it("reads a legacy baseline (no version, five fields per selection)", () => {
    localStorage.setItem(KEY, JSON.stringify(legacy));
    expect(readPriorCalculation("A")).toEqual(legacy);
  });

  it.each([
    ["not JSON", "{"],
    ["not an object", JSON.stringify("x")],
    ["an unknown version", JSON.stringify({ ...v2, version: 3 })],
    ["a non-array selections", JSON.stringify({ ...v2, selections: {} })],
    ["a non-object selection", JSON.stringify({ ...v2, selections: [7] })],
    [
      "a selection missing its sku",
      JSON.stringify({ ...legacy, selections: [{ service_code: "X" }] }),
    ],
    [
      "a non-string region",
      JSON.stringify({ ...v2, selections: [{ ...v2.selections[0], region: 5 }] }),
    ],
    [
      "non-object options",
      JSON.stringify({ ...v2, selections: [{ ...v2.selections[0], provider_options: "gcp" }] }),
    ],
  ])("drops %s", (_label, raw) => {
    localStorage.setItem(KEY, raw);
    expect(readPriorCalculation("A")).toBeNull();
  });
});
