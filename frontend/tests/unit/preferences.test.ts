import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PreferencesOut, PreferencesPatch } from "../../src/api/client";
import { readBrowserWorkspace } from "../../src/lib/browserPrefs";
import { PreferencesStore, effectiveWorkspace } from "../../src/lib/preferences";
import {
  needsCleaning,
  resolveChartSelection,
  moversNeedCleaning,
  resolveMoversSelection,
} from "../../src/lib/trends";

const CHARTS = {
  providers: [{ provider: "aws" as const, regions: ["us-east-1"] }],
  category: "all" as const,
};
const MOVERS = {
  provider: "gcp" as const,
  category: "compute" as const,
  regions: [],
  period_weeks: 52 as const,
};

function transport(stored: PreferencesOut["data"] = { migrated_from_browser: false }) {
  const patches: PreferencesPatch[] = [];
  let failures = 0;
  const t = {
    patches,
    failNext(n: number) {
      failures = n;
    },
    get: vi.fn(async (): Promise<PreferencesOut> => ({ schema_version: 1, data: stored })),
    patch: vi.fn(async (patch: PreferencesPatch): Promise<PreferencesOut> => {
      if (failures > 0) {
        failures -= 1;
        throw new Error("network down");
      }
      patches.push(patch);
      // Like the server: each section sent replaces that section.
      const { trends, ...rest } = patch;
      stored = { ...stored, ...rest } as PreferencesOut["data"];
      if (trends) stored = { ...stored, trends: { ...(stored.trends ?? {}), ...trends } };
      return { schema_version: 1, data: stored };
    }),
  };
  return t;
}

async function settle() {
  for (let i = 0; i < 5; i++) await Promise.resolve();
}

describe("PreferencesStore (019, FR-025)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("loads once", async () => {
    const t = transport({ migrated_from_browser: true, trends: { charts: CHARTS } });
    const store = new PreferencesStore(t);
    const [a, b] = await Promise.all([store.load(), store.load()]);
    await store.load();
    expect(t.get).toHaveBeenCalledTimes(1);
    expect(a).toBe(b);
    expect(store.current.trends?.charts).toEqual(CHARTS);
    expect(store.isLoaded).toBe(true);
  });

  it("applies a section patch at once and sends only that section", async () => {
    const t = transport({ migrated_from_browser: true, trends: { charts: CHARTS } });
    const store = new PreferencesStore(t);
    await store.load();
    const listener = vi.fn();
    store.subscribe(listener);
    store.patchSection("trends.movers", MOVERS);
    expect(store.current.trends).toEqual({ charts: CHARTS, movers: MOVERS });
    expect(listener).toHaveBeenCalled();
    await settle();
    expect(t.patches).toEqual([{ trends: { movers: MOVERS } }]);
  });

  it("queues a failed save and retries with backoff, never throwing", async () => {
    const t = transport();
    const store = new PreferencesStore(t, { baseDelayMs: 100, maxDelayMs: 1000 });
    t.failNext(2);
    expect(() => store.patchSection("workspace", { last_provider: "azure" })).not.toThrow();
    await settle();
    expect(t.patch).toHaveBeenCalledTimes(1);
    expect(store.queued).toEqual(["workspace"]);
    expect(store.current.workspace).toEqual({ last_provider: "azure" });

    await vi.advanceTimersByTimeAsync(99);
    expect(t.patch).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1); // first retry after 100 ms: fails again
    expect(t.patch).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(199);
    expect(t.patch).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1); // second retry after 200 ms: succeeds
    expect(t.patch).toHaveBeenCalledTimes(3);
    expect(t.patches).toEqual([{ workspace: { last_provider: "azure" } }]);
    expect(store.queued).toEqual([]);
  });

  it("keeps only the newest queued value of a section", async () => {
    const t = transport();
    const store = new PreferencesStore(t, { baseDelayMs: 100 });
    t.failNext(1);
    store.patchSection("trends.charts", CHARTS);
    await settle();
    store.patchSection("trends.charts", { providers: [], category: "storage" });
    store.patchSection("trends.movers", MOVERS);
    await vi.advanceTimersByTimeAsync(100);
    expect(t.patches).toEqual([
      { trends: { charts: { providers: [], category: "storage" }, movers: MOVERS } },
    ]);
  });

  it("a failed load keeps the defaults, keeps changes and can load again", async () => {
    const t = transport({ migrated_from_browser: true });
    t.get.mockRejectedValueOnce(new Error("offline"));
    const store = new PreferencesStore(t);
    await expect(store.load()).resolves.toEqual({ migrated_from_browser: false });
    store.patchSection("trends.charts", CHARTS);
    await settle();
    const loaded = await store.load();
    expect(t.get).toHaveBeenCalledTimes(2);
    expect(loaded).toEqual({ migrated_from_browser: true, trends: { charts: CHARTS } });
  });
});

// --- Moving the browser's old settings to the account, once (T091, FR-024) -------------------

describe("PreferencesStore browser migration (019, FR-023, FR-024)", () => {
  beforeEach(() => localStorage.clear());

  function browserValues() {
    localStorage.setItem(
      "cloud-pricing-column-widths",
      JSON.stringify({ provider: 300, collections: 410.4, service: -1, diagram: 9 }),
    );
    localStorage.setItem(
      "cloud-pricing-column-collapsed",
      JSON.stringify({ provider: true, service: "yes" }),
    );
  }

  it("reads only the valid old values, under the account keys", () => {
    browserValues();
    expect(readBrowserWorkspace()).toEqual({
      column_widths: { col1: 300, col2: 410 },
      collapsed: { col1: true },
    });
    localStorage.clear();
    expect(readBrowserWorkspace()).toBeNull();
  });

  it("sends the browser's values once, the account's own values winning, and sets the flag", async () => {
    browserValues();
    const t = transport({
      migrated_from_browser: false,
      workspace: { column_widths: { col1: 280 }, last_provider: "gcp" },
    });
    const store = new PreferencesStore(t, { readBrowser: readBrowserWorkspace });
    await store.load();
    await settle();
    expect(t.patches).toEqual([
      {
        workspace: {
          column_widths: { col1: 280, col2: 410 },
          collapsed: { col1: true },
          last_provider: "gcp",
        },
        migrated_from_browser: true,
      },
    ]);
    expect(store.current.migrated_from_browser).toBe(true);
    // A later load on another visit finds the flag set and sends nothing again.
    const again = new PreferencesStore(transport(store.current), {
      readBrowser: readBrowserWorkspace,
    });
    await again.load();
    await settle();
    expect(again.queued).toEqual([]);
  });

  it("sets the flag even when the browser has nothing to move", async () => {
    const t = transport({ migrated_from_browser: false });
    const store = new PreferencesStore(t, { readBrowser: readBrowserWorkspace });
    await store.load();
    await settle();
    expect(t.patches).toEqual([{ migrated_from_browser: true }]);
  });

  it("ignores the browser's values once the flag is set", async () => {
    browserValues();
    const readBrowser = vi.fn(readBrowserWorkspace);
    const t = transport({ migrated_from_browser: true, workspace: { collapsed: { col2: true } } });
    const store = new PreferencesStore(t, { readBrowser });
    await store.load();
    await settle();
    expect(t.patches).toEqual([]);
    expect(effectiveWorkspace(store.current, readBrowser)).toEqual({ collapsed: { col2: true } });
    expect(readBrowser).not.toHaveBeenCalled();
  });

  it("uses the browser's values until they are moved, also when loading fails", async () => {
    browserValues();
    const t = transport();
    t.get.mockRejectedValueOnce(new Error("offline"));
    const store = new PreferencesStore(t, { readBrowser: readBrowserWorkspace });
    expect(effectiveWorkspace(store.current, store.readBrowser).column_widths).toEqual({
      col1: 300,
      col2: 410,
    });
    await store.load();
    await settle();
    expect(store.isLoaded).toBe(false);
    expect(t.patches).toEqual([]);
    expect(effectiveWorkspace(store.current, store.readBrowser).collapsed).toEqual({ col1: true });
  });
});

describe("stale stored Trends values (019, data-model §1)", () => {
  const providers = [
    {
      code: "aws",
      name: "AWS",
      active: true,
      status: "current",
      reason: null,
      snapshot_date: "2026-10-12",
      snapshot_revision: 1,
    },
    {
      code: "azure",
      name: "Azure",
      active: false,
      status: "failed",
      reason: "x",
      snapshot_date: null,
      snapshot_revision: null,
    },
  ] as const;

  it("drops a provider or region no longer available and saves the cleaned value", async () => {
    const stored = {
      migrated_from_browser: true,
      trends: {
        charts: {
          providers: [
            { provider: "aws" as const, regions: ["us-east-1", "eu-gone-1"] },
            { provider: "azure" as const, regions: [] },
          ],
          category: "compute" as const,
        },
        movers: {
          provider: "azure" as const,
          category: "all" as const,
          regions: ["eastus"],
          period_weeks: 13 as const,
        },
      },
    };
    const t = transport(stored);
    const store = new PreferencesStore(t);
    await store.load();
    const known = { aws: ["us-east-1", "us-west-2"] };
    const charts = resolveChartSelection(store.current.trends?.charts, [...providers], known);
    const movers = resolveMoversSelection(store.current.trends?.movers, [...providers], known);
    if (needsCleaning(store.current.trends?.charts, charts))
      store.patchSection("trends.charts", charts);
    if (moversNeedCleaning(store.current.trends?.movers, movers))
      store.patchSection("trends.movers", movers);
    await settle();
    await settle();
    expect(store.current.trends).toEqual({
      charts: { providers: [{ provider: "aws", regions: ["us-east-1"] }], category: "compute" },
      movers: { provider: "aws", category: "all", regions: [], period_weeks: 13 },
    });
    expect(t.patches.flatMap((p) => Object.keys(p.trends ?? {}))).toEqual(["charts", "movers"]);
  });
});
