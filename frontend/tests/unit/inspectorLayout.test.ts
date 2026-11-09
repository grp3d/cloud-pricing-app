import { describe, expect, it, vi } from "vitest";

import type { PreferencesOut, PreferencesPatch } from "../../src/api/client";
import {
  DEFAULT_ARRANGEMENT,
  type InspectorArrangement,
  nextArrangement,
  other,
  readInspector,
  writeInspector,
} from "../../src/lib/inspectorLayout";
import { PreferencesStore } from "../../src/lib/preferences";

/** 021 data-model §1: every row of the state-transition table, merged and split. */

const merged = (front: "pricing" | "service" = "pricing"): InspectorArrangement => ({
  mode: "merged",
  upper: "pricing",
  front,
  split: 0.5,
});
const split = (upper: "pricing" | "service" = "pricing", s = 0.5): InspectorArrangement => ({
  mode: "split",
  upper,
  front: "pricing",
  split: s,
});

describe("inspectorLayout defaults", () => {
  it("starts merged with Pricing upper and in front, split 0.5", () => {
    expect(DEFAULT_ARRANGEMENT).toEqual({
      mode: "merged",
      upper: "pricing",
      front: "pricing",
      split: 0.5,
    });
  });

  it("other() swaps the two tabs", () => {
    expect(other("pricing")).toBe("service");
    expect(other("service")).toBe("pricing");
  });
});

describe("nextArrangement when merged", () => {
  it("select-tab brings that tab to the front", () => {
    expect(nextArrangement(merged(), { type: "select-tab", tab: "service" }).front).toBe("service");
  });

  it("drop-on-lower splits with the dragged tab below", () => {
    expect(nextArrangement(merged(), { type: "drop-on-lower", tab: "service" })).toMatchObject({
      mode: "split",
      upper: "pricing",
    });
    expect(nextArrangement(merged(), { type: "drop-on-lower", tab: "pricing" })).toMatchObject({
      mode: "split",
      upper: "service",
    });
  });

  it("drop-on-upper-bar, merge, swap and set-split change nothing", () => {
    const a = merged("service");
    expect(nextArrangement(a, { type: "drop-on-upper-bar", tab: "pricing" })).toBe(a);
    expect(nextArrangement(a, { type: "merge", tab: "pricing" })).toBe(a);
    expect(nextArrangement(a, { type: "swap" })).toBe(a);
    expect(nextArrangement(a, { type: "set-split", split: 0.3 })).toBe(a);
  });

  it("service-selected brings Service forward; calculation-finished brings Pricing", () => {
    expect(nextArrangement(merged("pricing"), { type: "service-selected" }).front).toBe("service");
    expect(nextArrangement(merged("service"), { type: "calculation-finished" }).front).toBe(
      "pricing",
    );
  });

  it("returns the same object when the event changes nothing", () => {
    const a = merged("service");
    expect(nextArrangement(a, { type: "service-selected" })).toBe(a);
    expect(nextArrangement(a, { type: "select-tab", tab: "service" })).toBe(a);
  });
});

describe("nextArrangement when split", () => {
  it("select-tab, service-selected and calculation-finished change nothing", () => {
    const a = split();
    expect(nextArrangement(a, { type: "select-tab", tab: "service" })).toBe(a);
    expect(nextArrangement(a, { type: "service-selected" })).toBe(a);
    expect(nextArrangement(a, { type: "calculation-finished" })).toBe(a);
  });

  it("drop-on-lower of the upper tab swaps; of the lower tab does nothing", () => {
    expect(nextArrangement(split("pricing"), { type: "drop-on-lower", tab: "pricing" }).upper).toBe(
      "service",
    );
    const a = split("pricing");
    expect(nextArrangement(a, { type: "drop-on-lower", tab: "service" })).toBe(a);
  });

  it("drop-on-upper-bar and merge merge with that tab in front", () => {
    expect(
      nextArrangement(split("pricing"), { type: "drop-on-upper-bar", tab: "service" }),
    ).toMatchObject({ mode: "merged", front: "service" });
    expect(nextArrangement(split("service"), { type: "merge", tab: "pricing" })).toMatchObject({
      mode: "merged",
      front: "pricing",
    });
  });

  it("swap exchanges the panes", () => {
    expect(nextArrangement(split("service"), { type: "swap" }).upper).toBe("pricing");
  });

  it("set-split clamps to [0.2, 0.8]", () => {
    expect(nextArrangement(split(), { type: "set-split", split: 0.35 }).split).toBe(0.35);
    expect(nextArrangement(split(), { type: "set-split", split: 0.05 }).split).toBe(0.2);
    expect(nextArrangement(split(), { type: "set-split", split: 0.95 }).split).toBe(0.8);
  });

  it("a split → merge → split round trip restores the previous upper tab", () => {
    const start = split("service", 0.3);
    const mergedBack = nextArrangement(start, { type: "merge", tab: "pricing" });
    expect(mergedBack.upper).toBe("service");
    // Splitting again from the keyboard menu on the front tab puts it below.
    const again = nextArrangement(mergedBack, { type: "drop-on-lower", tab: "pricing" });
    expect(again).toMatchObject({ mode: "split", upper: "service", split: 0.3 });
  });
});

function storeWith(data: PreferencesOut["data"]) {
  const patches: PreferencesPatch[] = [];
  const store = new PreferencesStore({
    get: vi.fn(async () => ({ schema_version: 1, data })),
    patch: vi.fn(async (p: PreferencesPatch) => {
      patches.push(p);
      return { schema_version: 1, data };
    }),
  });
  return { store, patches };
}

describe("readInspector / writeInspector", () => {
  it("falls back to the default when nothing or something invalid is stored", () => {
    expect(readInspector(undefined)).toEqual(DEFAULT_ARRANGEMENT);
    expect(readInspector({})).toEqual(DEFAULT_ARRANGEMENT);
    expect(
      readInspector({
        inspector: { mode: "tabs", upper: "pricing", front: "pricing", split: 0.5 },
      } as never),
    ).toEqual(DEFAULT_ARRANGEMENT);
    expect(
      readInspector({ inspector: { mode: "split", upper: "pricing", front: "pricing", split: 2 } }),
    ).toEqual(DEFAULT_ARRANGEMENT);
  });

  it("reads a stored arrangement", () => {
    const stored = { mode: "split", upper: "service", front: "pricing", split: 0.4 } as const;
    expect(readInspector({ inspector: stored })).toEqual(stored);
  });

  it("writes the arrangement, keeping the rest of the workspace section", async () => {
    const workspace = {
      column_widths: { col2: 300, col4: 380 },
      collapsed: { col2: true },
      last_provider: "gcp" as const,
    };
    const { store, patches } = storeWith({ migrated_from_browser: true, workspace });
    await store.load();
    const arrangement = split("service", 0.4);
    writeInspector(arrangement, store);
    expect(store.current.workspace).toEqual({ ...workspace, inspector: arrangement });
    await vi.waitFor(() => expect(store.queued).toEqual([]));
    expect(patches.at(-1)).toEqual({ workspace: { ...workspace, inspector: arrangement } });
  });
});
