/**
 * 027 US2 (FR-004 to FR-006, research R2, R3): the light and dark themes.
 *
 * - The theme is the `.dark` class on `<html>` (the colours in `index.css` follow it); absent
 *   means light.
 * - A logged-in user's choice is saved to their account (`appearance.theme`) through the
 *   preferences store, which applies it at once and retries a failed save. A guest's is applied
 *   for the session only: never sent, never cached (the server refuses it anyway).
 * - To avoid a light flash on reload, a logged-in user's theme is also cached in the browser
 *   with their ID; the inline script in `index.html` applies it before first paint when that ID
 *   is the current identity. The account's value, once loaded, wins.
 */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";

import type { Preferences } from "../api/client";
import { api } from "../api/client";
import { type PreferencesStore, preferencesStore, usePreferences } from "./preferences";

export type Theme = "light" | "dark";
export type ThemeIdentity = { loggedIn: boolean; userId: string | null };

/** Read by the pre-paint script in `index.html`: keep the two in step. */
export const THEME_CACHE_KEY = "cloud-pricing-theme";

const listeners = new Set<() => void>();

export function currentTheme(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

function applyTheme(theme: Theme): void {
  if (currentTheme() === theme) return;
  document.documentElement.classList.toggle("dark", theme === "dark");
  for (const listener of listeners) listener();
}

function writeCache(userId: string, theme: Theme): void {
  try {
    localStorage.setItem(THEME_CACHE_KEY, JSON.stringify({ user_id: userId, theme }));
  } catch {
    // Storage unavailable: the account's value still applies once loaded.
  }
}

export function clearThemeCache(): void {
  try {
    localStorage.removeItem(THEME_CACHE_KEY);
  } catch {
    // Nothing to clear.
  }
}

/** The user picked a theme in the user menu. */
export function setTheme(
  theme: Theme,
  who: ThemeIdentity,
  store: PreferencesStore = preferencesStore,
): void {
  applyTheme(theme);
  if (!who.loggedIn || !who.userId) return;
  store.patchSection("appearance", { theme });
  writeCache(who.userId, theme);
}

/** The account's preferences arrived (or changed): apply a user's saved theme. A guest keeps
 * whatever they chose this session, and no cache is kept for them. */
export function applyAccountTheme(prefs: Preferences, who: ThemeIdentity): void {
  if (!who.loggedIn || !who.userId) {
    clearThemeCache();
    return;
  }
  const theme = prefs.appearance?.theme ?? "light";
  applyTheme(theme);
  writeCache(who.userId, theme);
}

/** Log out: back to light, and forget the user's cached theme. */
export function resetTheme(): void {
  clearThemeCache();
  applyTheme("light");
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The theme in use, the identity it belongs to, and the setter. Applies the account's theme
 * once the preferences load. Mounted once, by the user menu. */
export function useTheme(): [Theme, (theme: Theme) => void] {
  const theme = useSyncExternalStore(subscribe, currentTheme);
  const [prefs, , loaded] = usePreferences();
  const currentUser = useQuery({ queryKey: ["currentUser"], queryFn: api.getCurrentUser });
  const user = currentUser.data;
  const who: ThemeIdentity = { loggedIn: Boolean(user?.username), userId: user?.id ?? null };

  useEffect(() => {
    if (!loaded || !user) return;
    applyAccountTheme(prefs, who);
    // `who` is derived from `user`; the saved theme is the only part of `prefs` that matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, user?.id, user?.username, prefs.appearance?.theme]);

  return [theme, (next) => setTheme(next, who)];
}
