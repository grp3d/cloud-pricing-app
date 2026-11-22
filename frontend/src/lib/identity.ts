/**
 * 027: what changes when the browser's identity changes (Log in, Log out). Every query is
 * identity-scoped and the preferences belong to one user, so every query is reset to its
 * initial state (active ones refetch for the new identity) and the preferences read again.
 */
import type { QueryClient } from "@tanstack/react-query";

import { preferencesStore } from "./preferences";

export function onIdentityChanged(queryClient: QueryClient): void {
  void queryClient.resetQueries();
  preferencesStore.reset();
  void preferencesStore.load();
}
