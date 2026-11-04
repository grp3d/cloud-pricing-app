/**
 * Trends page selections (019, FR-011, FR-020, data-model §1).
 *
 * The charts section is stored in preferences as `trends.charts`: providers, each with its
 * regions (none means all regions), and a category. An empty provider list means the defaults:
 * every available provider, all regions, all categories.
 */
import type {
  Provider,
  ProviderCode,
  TrendSeries,
  TrendsCategory,
  TrendsChartsPreferences,
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
