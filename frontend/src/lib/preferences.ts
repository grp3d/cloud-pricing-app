/**
 * Per-user preferences on the server (019, research R12, FR-020 to FR-025).
 *
 * - `load()` reads the record once; until it arrives (or if it fails) the defaults are used.
 * - `patchSection()` applies a change at once (optimistic) and queues it for saving. A section
 *   queued twice keeps only its newest value.
 * - A failed save never reaches the caller: it stays queued and is retried with backoff, so the
 *   change still applies for the session (FR-025).
 */
import { useSyncExternalStore } from "react";

import type {
  Preferences,
  PreferencesOut,
  PreferencesPatch,
  TrendsChartsPreferences,
  TrendsMoversPreferences,
  WorkspacePreferences,
} from "../api/client";
import { api } from "../api/client";

export type SectionValues = {
  migrated_from_browser: boolean;
  workspace: WorkspacePreferences | null;
  "trends.charts": TrendsChartsPreferences | null;
  "trends.movers": TrendsMoversPreferences | null;
};
export type Section = keyof SectionValues;

export interface PreferencesTransport {
  get: () => Promise<PreferencesOut>;
  patch: (patch: PreferencesPatch) => Promise<PreferencesOut>;
}

export interface StoreOptions {
  /** First retry delay; each later one doubles, up to `maxDelayMs`. */
  baseDelayMs?: number;
  maxDelayMs?: number;
}

export const DEFAULT_PREFERENCES: Preferences = { migrated_from_browser: false };

function withSection<S extends Section>(
  prefs: Preferences,
  section: S,
  value: SectionValues[S],
): Preferences {
  const next: Preferences = { ...prefs };
  if (section === "migrated_from_browser") {
    next.migrated_from_browser = value as boolean;
  } else if (section === "workspace") {
    if (value == null) delete next.workspace;
    else next.workspace = value as WorkspacePreferences;
  } else {
    const key = section === "trends.charts" ? "charts" : "movers";
    const trends = { ...(prefs.trends ?? {}) } as NonNullable<Preferences["trends"]>;
    if (value == null) delete trends[key];
    else (trends as Record<string, unknown>)[key] = value;
    if (Object.keys(trends).length === 0) delete next.trends;
    else next.trends = trends;
  }
  return next;
}

function patchBody(pending: Map<Section, unknown>): PreferencesPatch {
  const body: PreferencesPatch = {};
  const trends: Record<string, unknown> = {};
  for (const [section, value] of pending) {
    if (section === "migrated_from_browser") body.migrated_from_browser = value as boolean;
    else if (section === "workspace") body.workspace = value as WorkspacePreferences | null;
    else trends[section === "trends.charts" ? "charts" : "movers"] = value;
  }
  if (Object.keys(trends).length > 0) body.trends = trends as PreferencesPatch["trends"];
  return body;
}

export class PreferencesStore {
  private prefs: Preferences = DEFAULT_PREFERENCES;
  private loaded = false;
  private loading: Promise<Preferences> | null = null;
  private readonly listeners = new Set<() => void>();
  private readonly pending = new Map<Section, unknown>();
  private saving = false;
  private attempt = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly baseDelayMs: number;
  private readonly maxDelayMs: number;

  constructor(
    private readonly transport: PreferencesTransport,
    options: StoreOptions = {},
  ) {
    this.baseDelayMs = options.baseDelayMs ?? 1000;
    this.maxDelayMs = options.maxDelayMs ?? 60_000;
  }

  get current(): Preferences {
    return this.prefs;
  }

  get isLoaded(): boolean {
    return this.loaded;
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): Preferences => this.prefs;

  /** Load once; later calls return the same promise. Never rejects: on failure the defaults
   * (plus any changes already made) stay in use, and the next call tries again. */
  load(): Promise<Preferences> {
    if (this.loading) return this.loading;
    this.loading = this.transport
      .get()
      .then((out) => {
        // Changes made before the record arrived win over the stored values.
        let prefs = out.data;
        for (const [section, value] of this.pending) {
          prefs = withSection(prefs, section, value as SectionValues[typeof section]);
        }
        this.loaded = true;
        this.set(prefs);
        return prefs;
      })
      .catch(() => {
        this.loading = null;
        return this.prefs;
      });
    return this.loading;
  }

  /** Apply now, save in the background. Never throws (FR-025). */
  patchSection<S extends Section>(section: S, value: SectionValues[S]): void {
    this.set(withSection(this.prefs, section, value));
    this.pending.delete(section); // keep queue order by last change
    this.pending.set(section, value);
    void this.flush();
  }

  /** Sections waiting to be saved (for tests and diagnostics). */
  get queued(): Section[] {
    return [...this.pending.keys()];
  }

  private set(prefs: Preferences): void {
    this.prefs = prefs;
    for (const listener of this.listeners) listener();
  }

  private async flush(): Promise<void> {
    if (this.saving || this.retryTimer !== null || this.pending.size === 0) return;
    this.saving = true;
    const sending = new Map(this.pending);
    try {
      await this.transport.patch(patchBody(sending));
      // Drop what was saved, unless it changed again while saving.
      for (const [section, value] of sending) {
        if (this.pending.get(section) === value) this.pending.delete(section);
      }
      this.attempt = 0;
    } catch {
      const delay = Math.min(this.baseDelayMs * 2 ** this.attempt, this.maxDelayMs);
      this.attempt += 1;
      this.retryTimer = setTimeout(() => {
        this.retryTimer = null;
        void this.flush();
      }, delay);
    } finally {
      this.saving = false;
    }
    if (this.retryTimer === null && this.pending.size > 0) void this.flush();
  }
}

export const preferencesStore = new PreferencesStore({
  get: api.getPreferences,
  patch: api.patchPreferences,
});

/** The current preferences (re-rendering on change) and the section setter. Starts the load
 * on first use. */
export function usePreferences(
  store: PreferencesStore = preferencesStore,
): [Preferences, PreferencesStore["patchSection"], boolean] {
  const prefs = useSyncExternalStore(store.subscribe, store.getSnapshot);
  void store.load();
  return [prefs, store.patchSection.bind(store), store.isLoaded];
}
