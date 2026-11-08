import { describe, expect, it } from "vitest";

import {
  decideBaselineUpdate,
  pricedContentsEqual,
  type PriceChangeSelection,
  type PricedContentsEntry,
  type PriorCalculation,
} from "../../src/lib/priceChange";

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

  it('flags a duration-only adjustment when only the Duration selection changed (009, FR-002/003 — supersedes 008\'s FR-016, which wrongly left this case as "unchanged")', () => {
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

// 015-canvas-service-icons, FR-018a, research.md §7: "out of date" comparison.
describe("pricedContentsEqual", () => {
  function entry(overrides: Partial<PricedContentsEntry> = {}): PricedContentsEntry {
    return { ...selection(), region: "us-east-1", ...overrides };
  }

  it("is order-independent", () => {
    const a = entry({ sku: "A" });
    const b = entry({ sku: "B" });
    expect(pricedContentsEqual([a, b], [b, a])).toBe(true);
  });

  it.each([
    ["usage_quantity", { usage_quantity: "2" }],
    ["pricing_term", { pricing_term: "reserved_1yr" as const }],
    ["purchase_option", { purchase_option: "all_upfront" as const }],
    ["sku", { sku: "OTHER" }],
    ["service_code", { service_code: "AmazonS3" }],
    ["region", { region: "eu-west-1" }],
  ])("detects a change in %s", (_field, overrides) => {
    expect(pricedContentsEqual([entry()], [entry(overrides)])).toBe(false);
  });

  it("detects added or removed services", () => {
    expect(pricedContentsEqual([entry()], [entry(), entry({ sku: "B" })])).toBe(false);
  });

  it("compares as a multiset (duplicates count)", () => {
    expect(pricedContentsEqual([entry(), entry()], [entry(), entry({ sku: "B" })])).toBe(false);
    expect(pricedContentsEqual([entry(), entry()], [entry(), entry()])).toBe(true);
  });
});

// --- 020 (T004, research R1/R3, data-model §3/§4) --------------------------------------------

const GCP_MACHINE = {
  kind: "gcp_machine" as const,
  version: 1 as const,
  vcpus: 4,
  memory_gib: "16",
  ram_sku: "RAM",
};
const AZURE_LINUX = { kind: "azure_vm" as const, version: 1 as const, os: "linux" as const };

function v2Selection(overrides: Partial<PriceChangeSelection> = {}): PriceChangeSelection {
  return selection({
    service_code: "6F81-5844-456A",
    sku: "CORE",
    region: "us-east1",
    provider_options: GCP_MACHINE,
    ...overrides,
  });
}

function v2Prior(overrides: Partial<PriorCalculation> = {}): PriorCalculation {
  return prior({ version: 2, selections: [v2Selection()], ...overrides });
}

describe("decideBaselineUpdate with version 2 baselines (020)", () => {
  it.each([
    ["vCPUs", { provider_options: { ...GCP_MACHINE, vcpus: 8 } }],
    ["memory", { provider_options: { ...GCP_MACHINE, memory_gib: "32" } }],
    ["region", { region: "europe-west1" }],
  ])("counts a change to only %s as a content change", (_label, change) => {
    const current = [v2Selection(change)];
    expect(
      decideBaselineUpdate({
        prior: v2Prior(),
        currentSelections: current,
        newDuration: "1_month",
        provider: "gcp",
      }),
    ).toBe("direct");
    expect(
      decideBaselineUpdate({
        prior: v2Prior(),
        currentSelections: current,
        newDuration: "1_year",
        provider: "gcp",
      }),
    ).toBe("duration_adjusted");
  });

  it("counts a change to only the Azure OS as a content change", () => {
    const vm = (os: "linux" | "windows") =>
      v2Selection({
        service_code: "VM",
        region: "eastus",
        provider_options: { ...AZURE_LINUX, os },
      });
    expect(
      decideBaselineUpdate({
        prior: v2Prior({ selections: [vm("linux")] }),
        currentSelections: [vm("windows")],
        newDuration: "1_month",
        provider: "azure",
      }),
    ).toBe("direct");
  });

  it("treats the same options in a different key order as unchanged", () => {
    const reordered = {
      ram_sku: "RAM",
      memory_gib: "16",
      vcpus: 4,
      version: 1 as const,
      kind: "gcp_machine" as const,
    };
    expect(
      decideBaselineUpdate({
        prior: v2Prior(),
        currentSelections: [v2Selection({ provider_options: reordered })],
        newDuration: "1_month",
        provider: "gcp",
      }),
    ).toBe("unchanged");
  });

  it("treats a value edited and put back as unchanged", () => {
    expect(
      decideBaselineUpdate({
        prior: v2Prior(),
        currentSelections: [v2Selection({ provider_options: { ...GCP_MACHINE } })],
        newDuration: "1_month",
        provider: "gcp",
      }),
    ).toBe("unchanged");
  });

  it("treats a missing region or options the same as null", () => {
    const bare = selection({ region: null, provider_options: null });
    expect(
      decideBaselineUpdate({
        prior: v2Prior({ selections: [bare] }),
        currentSelections: [selection()],
        newDuration: "1_month",
        provider: "aws",
      }),
    ).toBe("unchanged");
  });

  it("re-prices a v2 GCP baseline after a Duration switch (never unavailable)", () => {
    expect(
      decideBaselineUpdate({
        prior: v2Prior(),
        currentSelections: [v2Selection()],
        newDuration: "1_year",
        provider: "gcp",
      }),
    ).toBe("duration_only");
  });
});

describe("decideBaselineUpdate with legacy baselines (020, FR-005)", () => {
  // A v0.0.2 baseline: no `version`, and selections with only the original five fields.
  const legacy = prior({
    selections: [selection({ service_code: "6F81-5844-456A", sku: "CORE" })],
  });

  it("compares on the original five fields only, so the upgrade alone isn't a change", () => {
    expect(
      decideBaselineUpdate({
        prior: legacy,
        currentSelections: [v2Selection()],
        newDuration: "1_month",
        provider: "gcp",
      }),
    ).toBe("unchanged");
    expect(
      decideBaselineUpdate({
        prior: legacy,
        currentSelections: [v2Selection({ usage_quantity: "2" })],
        newDuration: "1_month",
        provider: "gcp",
      }),
    ).toBe("direct");
  });

  it.each(["gcp", "azure"] as const)(
    "is unavailable after a Duration switch on %s, changed or not",
    (provider) => {
      for (const current of [[v2Selection()], [v2Selection({ usage_quantity: "2" })]]) {
        expect(
          decideBaselineUpdate({
            prior: legacy,
            currentSelections: current,
            newDuration: "1_year",
            provider,
          }),
        ).toBe("unavailable");
      }
    },
  );

  it("re-prices as today after a Duration switch on aws", () => {
    const awsLegacy = prior();
    expect(
      decideBaselineUpdate({
        prior: awsLegacy,
        currentSelections: [selection({ region: "us-east-1", provider_options: null })],
        newDuration: "1_year",
        provider: "aws",
      }),
    ).toBe("duration_only");
    expect(
      decideBaselineUpdate({
        prior: awsLegacy,
        currentSelections: [selection({ usage_quantity: "3", region: "us-east-1" })],
        newDuration: "1_year",
        provider: "aws",
      }),
    ).toBe("duration_adjusted");
  });

  it("defaults the provider to aws when none is given", () => {
    expect(
      decideBaselineUpdate({
        prior: prior(),
        currentSelections: [selection()],
        newDuration: "1_year",
      }),
    ).toBe("duration_only");
  });
});

describe("pricedContentsEqual with provider options (020)", () => {
  function v2Entry(overrides: Partial<PricedContentsEntry> = {}): PricedContentsEntry {
    return { ...v2Selection(), region: "us-east1", ...overrides };
  }

  it("compares provider_options for version 2 entries", () => {
    expect(pricedContentsEqual([v2Entry()], [v2Entry()])).toBe(true);
    expect(
      pricedContentsEqual(
        [v2Entry()],
        [v2Entry({ provider_options: { ...GCP_MACHINE, vcpus: 8 } })],
      ),
    ).toBe(false);
  });

  it("ignores provider_options when the stored entries are legacy (no field)", () => {
    const legacyEntry: PricedContentsEntry = v2Entry();
    delete legacyEntry.provider_options;
    expect(pricedContentsEqual([legacyEntry], [v2Entry()])).toBe(true);
    expect(pricedContentsEqual([legacyEntry], [v2Entry({ usage_quantity: "9" })])).toBe(false);
  });
});
