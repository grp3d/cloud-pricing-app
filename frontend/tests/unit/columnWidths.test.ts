import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PreferencesOut, PreferencesPatch } from "../../src/api/client";
import { readBrowserWorkspace } from "../../src/lib/browserPrefs";
import { readColumnWidths, writeColumnWidth } from "../../src/lib/columnWidths";
import { PreferencesStore } from "../../src/lib/preferences";

/** 019 (FR-023): widths are the `workspace.column_widths` preferences section. */
function storeWith(data: PreferencesOut["data"] = { migrated_from_browser: true }) {
  const patches: PreferencesPatch[] = [];
  const store = new PreferencesStore(
    {
      get: vi.fn(async () => ({ schema_version: 1, data })),
      patch: vi.fn(async (p: PreferencesPatch) => {
        patches.push(p);
        return { schema_version: 1, data };
      }),
    },
    { readBrowser: readBrowserWorkspace },
  );
  return { store, patches };
}

describe("columnWidths (preferences-backed)", () => {
  beforeEach(() => localStorage.clear());

  it("returns an empty object when nothing is stored", async () => {
    const { store } = storeWith();
    await store.load();
    expect(readColumnWidths(store)).toEqual({});
  });

  it("reads the account's widths under the column keys", async () => {
    const { store } = storeWith({
      migrated_from_browser: true,
      workspace: { column_widths: { col2: 400, col4: 300 } },
    });
    await store.load();
    expect(readColumnWidths(store)).toEqual({ collections: 400, pricing: 300 });
  });

  it("writes one column at once, keeping the others, and saves it to the account", async () => {
    const { store, patches } = storeWith({
      migrated_from_browser: true,
      workspace: { column_widths: { col1: 250 }, last_provider: "gcp" },
    });
    await store.load();
    writeColumnWidth("collections", 400.6, store);
    writeColumnWidth("service", 350, store);
    expect(readColumnWidths(store)).toEqual({ provider: 250, collections: 401, service: 350 });
    await vi.waitFor(() => expect(store.queued).toEqual([]));
    expect(patches.at(-1)).toEqual({
      workspace: { column_widths: { col1: 250, col2: 401, col3: 350 }, last_provider: "gcp" },
    });
    // Never written to the browser any more.
    expect(localStorage.getItem("cloud-pricing-column-widths")).toBeNull();
  });

  it("uses this browser's old widths until they are moved, then the account's", async () => {
    localStorage.setItem(
      "cloud-pricing-column-widths",
      JSON.stringify({ service: 350, pricing: "wide", provider: -5 }),
    );
    const { store } = storeWith({ migrated_from_browser: false });
    expect(readColumnWidths(store)).toEqual({ service: 350 });
    await store.load();
    expect(store.current.migrated_from_browser).toBe(true);
    expect(store.current.workspace?.column_widths).toEqual({ col3: 350 });
    localStorage.clear();
    expect(readColumnWidths(store)).toEqual({ service: 350 });
  });

  it("ignores old browser widths once the account says they were moved", async () => {
    localStorage.setItem("cloud-pricing-column-widths", JSON.stringify({ service: 350 }));
    const { store } = storeWith({ migrated_from_browser: true });
    await store.load();
    expect(readColumnWidths(store)).toEqual({});
  });
});
