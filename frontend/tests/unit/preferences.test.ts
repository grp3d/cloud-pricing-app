import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PreferencesOut, PreferencesPatch } from "../../src/api/client";
import { PreferencesStore } from "../../src/lib/preferences";

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
    const t = transport({ migrated_from_browser: false, trends: { charts: CHARTS } });
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
