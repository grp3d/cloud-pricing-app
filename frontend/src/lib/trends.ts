/**
 * Trends page selections (019, FR-011, FR-020, data-model §1).
 *
 * The charts section is stored in preferences as `trends.charts`: providers, each with its
 * regions (none means all regions), and a category. An empty provider list means the defaults:
 * every available provider, all regions, all categories.
 *
 * The movers section is `trends.movers`: one provider, a category, regions and a period. A
 * missing section means its defaults: the first available provider, all categories, all
 * regions, 52 weeks.
 */
import type {
  Movers,
  Provider,
  ProviderCode,
  TrendSeries,
  TrendsCategory,
  TrendsChartsPreferences,
  TrendsMoversPreferences,
} from "../api/client";
import { PROVIDER_LABELS, asProviderCode } from "./providerPricing";

export interface ChartSelection {
  providers: { provider: ProviderCode; regions: string[] }[];
  category: TrendsCategory;
}

export const CATEGORY_LABELS: Record<TrendsCategory, string> = {
  all: "All categories",
  compute: "Compute",
  storage: "Storage",
  database: "Database",
  networking: "Networking",
};

/** What Reset stores (FR-020): the defaults for the charts section only. */
export const CHARTS_DEFAULTS: TrendsChartsPreferences = { providers: [], category: "all" };

/** The selection to show: the stored one, cleaned of providers and regions no longer
 * available, or every active provider with all regions. */
export function resolveChartSelection(
  stored: TrendsChartsPreferences | null | undefined,
  providers: Provider[],
  regionsByProvider: Partial<Record<ProviderCode, string[]>>,
): ChartSelection {
  const active = providers.filter((p) => p.active).map((p) => p.code as ProviderCode);
  const kept = (stored?.providers ?? [])
    .filter((p) => active.includes(p.provider))
    .map((p) => {
      const known = regionsByProvider[p.provider];
      const regions = known
        ? (p.regions ?? []).filter((r) => known.includes(r))
        : (p.regions ?? []);
      return { provider: p.provider, regions };
    });
  return {
    providers: kept.length > 0 ? kept : active.map((provider) => ({ provider, regions: [] })),
    category: stored?.category ?? "all",
  };
}

/** `select` query values for `GET /trends/series`. */
export function selectParams(selection: ChartSelection): string[] {
  return selection.providers.map((p) => `${p.provider}:${p.regions.join(",")}`);
}

/** Whether a stored value differs from what was resolved (it is then saved back cleaned). */
export function needsCleaning(
  stored: TrendsChartsPreferences | null | undefined,
  resolved: ChartSelection,
): boolean {
  if (!stored || stored.providers.length === 0) return false;
  return JSON.stringify(stored.providers) !== JSON.stringify(resolved.providers);
}

export function seriesTitle(series: TrendSeries): string {
  const name = PROVIDER_LABELS[asProviderCode(series.provider)];
  return `${name} — ${series.regions.length > 0 ? series.regions.join(", ") : "all regions"}`;
}

export function statusNote(series: TrendSeries): string | null {
  switch (series.status) {
    case "building":
      return `Building history (${series.weeks_built} of ${series.weeks_total} weeks)`;
    case "not_enough_history":
      return "Not enough history yet: at least two weekly snapshots are needed.";
    case "provider_unavailable":
      return `Pricing data unavailable${series.reason ? `: ${series.reason}` : ""}.`;
    default:
      return null;
  }
}

// --- Movers (019, US3, FR-016 to FR-020) ------------------------------------------------------

export type MoversPeriod = 1 | 4 | 13 | 52;

export interface MoversSelection {
  provider: ProviderCode;
  category: TrendsCategory;
  regions: string[];
  period_weeks: MoversPeriod;
}

export const MOVERS_PERIODS: { weeks: MoversPeriod; label: string }[] = [
  { weeks: 1, label: "Last week" },
  { weeks: 4, label: "Last 4 weeks" },
  { weeks: 13, label: "Last 13 weeks" },
  { weeks: 52, label: "Last 52 weeks" },
];

/** The movers selection to show, or null when no provider is available. A stored provider no
 * longer available falls back to the first available one, with all regions; a stored region no
 * longer available is dropped. */
export function resolveMoversSelection(
  stored: TrendsMoversPreferences | null | undefined,
  providers: Provider[],
  regionsByProvider: Partial<Record<ProviderCode, string[]>>,
): MoversSelection | null {
  const active = providers.filter((p) => p.active).map((p) => p.code as ProviderCode);
  if (active.length === 0) return null;
  const keep = stored && active.includes(stored.provider);
  const provider = keep ? stored.provider : active[0];
  const known = regionsByProvider[provider];
  const regions = keep ? (stored.regions ?? []).filter((r) => !known || known.includes(r)) : [];
  return {
    provider,
    category: stored?.category ?? "all",
    regions,
    period_weeks: stored?.period_weeks ?? 52,
  };
}

/** Whether a stored movers value differs from what was resolved (it is then saved back). */
export function moversNeedCleaning(
  stored: TrendsMoversPreferences | null | undefined,
  resolved: MoversSelection | null,
): boolean {
  if (!stored || !resolved) return false;
  return stored.provider !== resolved.provider || stored.regions.join() !== resolved.regions.join();
}

/** "+10.00%" / "−5.56%". */
export function formatChangePct(pct: number): string {
  return `${pct > 0 ? "+" : pct < 0 ? "\u2212" : ""}${Math.abs(pct).toFixed(2)}%`;
}

/** Which weeks the lists compare, or why they are empty (spec Edge Cases). */
export function moversNote(movers: Movers): string | null {
  switch (movers.status) {
    case "building":
      return "Building history: the lists cover the weeks built so far.";
    case "not_enough_history":
      return "Not enough history yet: at least two weekly snapshots are needed.";
    case "provider_unavailable":
      return `Pricing data unavailable${movers.reason ? `: ${movers.reason}` : ""}.`;
    default:
      break;
  }
  if (!movers.from_snapshot || !movers.to_snapshot) return null;
  const weeks = `${movers.weeks_available} week${movers.weeks_available === 1 ? "" : "s"}`;
  const shorter =
    movers.weeks_available < movers.period_weeks ? ` (only ${weeks} of history so far)` : "";
  return `Compares ${movers.from_snapshot} with ${movers.to_snapshot}${shorter || `, ${weeks}`}.`;
}
