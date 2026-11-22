import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PreferencesOut, PreferencesPatch } from "../../src/api/client";
import { PreferencesStore } from "../../src/lib/preferences";
import {
  THEME_CACHE_KEY,
  applyAccountTheme,
  clearThemeCache,
  currentTheme,
  setTheme,
} from "../../src/lib/theme";

/** 027 US2 (FR-004 to FR-006, research R2, R3): applying, saving and caching the theme. */

const IDENTITY_KEY = "cloud-pricing-current-identity-id";
const USER = { loggedIn: true, userId: "u1" };
const GUEST = { loggedIn: false, userId: "g1" };

function transport(fail = false) {
  const patches: PreferencesPatch[] = [];
  return {
    patches,
    get: vi.fn(async (): Promise<PreferencesOut> => ({
      schema_version: 1,
      data: { migrated_from_browser: true },
    })),
    patch: vi.fn(async (patch: PreferencesPatch): Promise<PreferencesOut> => {
      if (fail) throw new Error("network down");
      patches.push(patch);
      return { schema_version: 1, data: { migrated_from_browser: true } };
    }),
  };
}

const isDark = () => document.documentElement.classList.contains("dark");
const cached = () => JSON.parse(localStorage.getItem(THEME_CACHE_KEY) ?? "null");

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});
afterEach(() => vi.useRealTimers());

describe("theme", () => {
  it("is light when nothing was chosen", () => {
    expect(currentTheme()).toBe("light");
    expect(isDark()).toBe(false);
  });

  it("switches the whole page at once and saves it for a logged-in user", async () => {
    const t = transport();
    const store = new PreferencesStore(t);
    setTheme("dark", USER, store);
    expect(isDark()).toBe(true);
    expect(currentTheme()).toBe("dark");
    await vi.waitFor(() => expect(t.patches).toEqual([{ appearance: { theme: "dark" } }]));
    expect(cached()).toEqual({ user_id: "u1", theme: "dark" });

    setTheme("light", USER, store);
    expect(isDark()).toBe(false);
    expect(cached()).toEqual({ user_id: "u1", theme: "light" });
  });

  it("applies but never saves or caches a guest's theme", async () => {
    const t = transport();
    const store = new PreferencesStore(t);
    setTheme("dark", GUEST, store);
    expect(isDark()).toBe(true);
    await Promise.resolve();
    expect(t.patch).not.toHaveBeenCalled();
    expect(store.queued).toEqual([]);
    expect(localStorage.getItem(THEME_CACHE_KEY)).toBeNull();
  });

  it("keeps the theme applied when saving fails", async () => {
    vi.useFakeTimers();
    const t = transport(true);
    const store = new PreferencesStore(t);
    setTheme("dark", USER, store);
    await vi.advanceTimersByTimeAsync(0);
    expect(isDark()).toBe(true);
    expect(store.queued).toEqual(["appearance"]);
  });

  it("applies the account's theme for a user and refreshes the cache", () => {
    applyAccountTheme({ migrated_from_browser: true, appearance: { theme: "dark" } }, USER);
    expect(isDark()).toBe(true);
    expect(cached()).toEqual({ user_id: "u1", theme: "dark" });
    applyAccountTheme({ migrated_from_browser: true }, USER);
    expect(isDark()).toBe(false);
    expect(cached()).toEqual({ user_id: "u1", theme: "light" });
  });

  it("leaves a guest's in-session choice alone and clears any cache", () => {
    localStorage.setItem(THEME_CACHE_KEY, JSON.stringify({ user_id: "u1", theme: "dark" }));
    setTheme("dark", GUEST, new PreferencesStore(transport()));
    applyAccountTheme({ migrated_from_browser: true }, GUEST);
    expect(isDark()).toBe(true);
    expect(localStorage.getItem(THEME_CACHE_KEY)).toBeNull();
  });

  it("clearThemeCache removes the cache", () => {
    localStorage.setItem(THEME_CACHE_KEY, JSON.stringify({ user_id: "u1", theme: "dark" }));
    clearThemeCache();
    expect(localStorage.getItem(THEME_CACHE_KEY)).toBeNull();
  });
});

describe("the pre-paint script in index.html (research R3)", () => {
  const html = readFileSync(resolve(__dirname, "../../index.html"), "utf8");
  const script = /<script>([\s\S]*?)<\/script>/.exec(html)?.[1] ?? "";
  const run = () => new Function(script)();

  it("exists", () => expect(script).toContain(THEME_CACHE_KEY));

  it("applies dark before first paint when the cache is the current identity's", () => {
    localStorage.setItem(IDENTITY_KEY, "u1");
    localStorage.setItem(THEME_CACHE_KEY, JSON.stringify({ user_id: "u1", theme: "dark" }));
    run();
    expect(isDark()).toBe(true);
  });

  it("does nothing for another identity, a light cache, or a broken entry", () => {
    localStorage.setItem(IDENTITY_KEY, "g1");
    localStorage.setItem(THEME_CACHE_KEY, JSON.stringify({ user_id: "u1", theme: "dark" }));
    run();
    expect(isDark()).toBe(false);
    localStorage.setItem(IDENTITY_KEY, "u1");
    localStorage.setItem(THEME_CACHE_KEY, JSON.stringify({ user_id: "u1", theme: "light" }));
    run();
    expect(isDark()).toBe(false);
    localStorage.setItem(THEME_CACHE_KEY, "{not json");
    expect(run).not.toThrow();
    expect(isDark()).toBe(false);
  });
});
