import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PreferencesOut, PreferencesPatch } from "../../src/api/client";
import { readBrowserWorkspace } from "../../src/lib/browserPrefs";
import { readColumnCollapsed, writeColumnCollapsed } from "../../src/lib/columnCollapse";
import { PreferencesStore } from "../../src/lib/preferences";

/** 019 (FR-023): collapsed flags are the `workspace.collapsed` preferences section. */
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

describe("columnCollapse (preferences-backed)", () => {
  beforeEach(() => localStorage.clear());

  it("returns an empty object when nothing is stored", async () => {
    const { store } = storeWith();
    await store.load();
    expect(readColumnCollapsed(store)).toEqual({});
  });

  it("round-trips a written flag, including an explicit false", async () => {
    const { store, patches } = storeWith();
    await store.load();
    writeColumnCollapsed("collections", true, store);
    expect(readColumnCollapsed(store)).toEqual({ collections: true });
    writeColumnCollapsed("collections", false, store);
    expect(readColumnCollapsed(store)).toEqual({ collections: false });
    await vi.waitFor(() => expect(store.queued).toEqual([]));
    expect(patches.at(-1)).toEqual({ workspace: { collapsed: { col2: false } } });
  });

  it("keeps each column's flag independent of the others", async () => {
    const { store } = storeWith({
      migrated_from_browser: true,
      workspace: { collapsed: { col1: true } },
    });
    await store.load();
    writeColumnCollapsed("service", false, store);
    expect(readColumnCollapsed(store)).toEqual({ provider: true, service: false });
  });

  it("uses this browser's old flags until they are moved, skipping invalid ones", async () => {
    localStorage.setItem(
      "cloud-pricing-column-collapsed",
      JSON.stringify({ collections: "yes", service: 1, provider: true }),
    );
    const { store } = storeWith({ migrated_from_browser: false });
    expect(readColumnCollapsed(store)).toEqual({ provider: true });
    await store.load();
    expect(store.current.workspace?.collapsed).toEqual({ col1: true });
  });

  it("falls back to an empty object for malformed browser data, rather than throwing", () => {
    localStorage.setItem("cloud-pricing-column-collapsed", "not json");
    const { store } = storeWith({ migrated_from_browser: false });
    expect(readColumnCollapsed(store)).toEqual({});
  });
});
