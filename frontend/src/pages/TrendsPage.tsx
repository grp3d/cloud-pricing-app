import { useQueries, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";

import { type ProviderCode, type Region, api } from "../api/client";
import { ErrorMessage } from "../components/ErrorMessage";
import { ChartSelectors } from "../components/trends/ChartSelectors";
import { MoversPanel } from "../components/trends/MoversPanel";
import { TrendsChartPanel } from "../components/trends/TrendsChartPanel";
import { usePreferences } from "../lib/preferences";
import {
  CHARTS_DEFAULTS,
  type ChartSelection,
  type MoversSelection,
  moversNeedCleaning,
  needsCleaning,
  resolveChartSelection,
  resolveMoversSelection,
  selectParams,
} from "../lib/trends";

/**
 * The Trends page (019, FR-010): the charts section on the left (SKUs Changed per provider,
 * US2) and the biggest movers on the right (US3). Each section's selections are saved to the
 * user's preferences (`trends.charts`, `trends.movers`), restored on any device, and cleaned of
 * providers or regions no longer available. Each Reset touches only its own section (FR-020).
 */
export function TrendsPage() {
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.listProviders });
  const active = useMemo(() => (providers.data ?? []).filter((p) => p.active), [providers.data]);
  const regionQueries = useQueries({
    queries: active.map((p) => ({
      queryKey: ["regions", p.code],
      queryFn: () => api.listRegions(p.code as ProviderCode),
    })),
  });
  const regionsByProvider = useMemo(() => {
    const out: Partial<Record<ProviderCode, Region[]>> = {};
    active.forEach((p, i) => {
      const data = regionQueries[i]?.data;
      if (data) out[p.code as ProviderCode] = data.regions;
    });
    return out;
  }, [active, regionQueries]);
  const regionCodes = useMemo(() => {
    const out: Partial<Record<ProviderCode, string[]>> = {};
    for (const [code, regions] of Object.entries(regionsByProvider)) {
      out[code as ProviderCode] = (regions ?? []).map((r) => r.code);
    }
    return out;
  }, [regionsByProvider]);

  const [prefs, patchSection, prefsLoaded] = usePreferences();
  const stored = prefs.trends?.charts;
  const selection = resolveChartSelection(stored, providers.data ?? [], regionCodes);

  // A stored provider or region that is no longer available is dropped and saved back.
  const regionsReady = regionQueries.every((q) => q.isSuccess);
  useEffect(() => {
    if (prefsLoaded && providers.isSuccess && regionsReady && needsCleaning(stored, selection)) {
      patchSection("trends.charts", selection);
    }
  }, [prefsLoaded, providers.isSuccess, regionsReady, stored, selection, patchSection]);

  const storedMovers = prefs.trends?.movers;
  const moversSelection = resolveMoversSelection(storedMovers, providers.data ?? [], regionCodes);
  useEffect(() => {
    if (
      prefsLoaded &&
      providers.isSuccess &&
      regionsReady &&
      moversNeedCleaning(storedMovers, moversSelection)
    ) {
      patchSection("trends.movers", moversSelection);
    }
  }, [prefsLoaded, providers.isSuccess, regionsReady, storedMovers, moversSelection, patchSection]);

  const select = selectParams(selection);
  const series = useQuery({
    queryKey: ["trends", "series", select, selection.category],
    queryFn: () => api.getTrendSeries(select, selection.category),
    enabled: providers.isSuccess && select.length > 0,
    // While a provider's history is being built, refresh to show the weeks as they arrive.
    refetchInterval: (query) =>
      query.state.data?.series.some((s) => s.status === "building") ? 15_000 : false,
  });

  function change(next: ChartSelection) {
    patchSection("trends.charts", next);
  }

  function changeMovers(next: MoversSelection) {
    patchSection("trends.movers", next);
  }

  return (
    <div className="flex h-full min-h-0 gap-4 overflow-auto p-3">
      <section aria-labelledby="trends-charts" className="flex min-w-0 flex-[3] flex-col gap-3">
        <div>
          <h2 id="trends-charts" className="text-xs font-semibold">
            SKUs changed per week
          </h2>
          <p className="text-2xs text-muted-foreground">
            The number of SKUs whose on-demand list price went up or down between consecutive weekly
            snapshots, over up to the last 52 weeks. Only SKUs with a non-zero price in both weeks
            are compared.
          </p>
        </div>
        {providers.isError && (
          <ErrorMessage message={providers.error.message} onRetry={() => providers.refetch()} />
        )}
        {providers.isSuccess && (
          <ChartSelectors
            providers={active}
            regionsByProvider={regionsByProvider}
            selection={selection}
            onChange={change}
            onReset={() => patchSection("trends.charts", CHARTS_DEFAULTS)}
          />
        )}
        {series.isError && (
          <ErrorMessage message={series.error.message} onRetry={() => series.refetch()} />
        )}
        {series.isLoading && <p className="text-2xs text-muted-foreground">Loading…</p>}
        {series.data && <TrendsChartPanel series={series.data.series} />}
        {providers.isSuccess && select.length === 0 && <TrendsChartPanel series={[]} />}
      </section>
      <section
        aria-labelledby="trends-movers"
        className="flex min-w-0 flex-[2] flex-col gap-2 border-l border-border pl-4"
      >
        <h2 id="trends-movers" className="text-xs font-semibold">
          Biggest movers
        </h2>
        <p className="text-2xs text-muted-foreground">
          The 3 largest on-demand list price increases and decreases, as a % of the price at the
          start of the period. Each region is a separate entry.
        </p>
        {providers.isSuccess && !moversSelection && (
          <p className="text-2xs text-muted-foreground">No provider has pricing data.</p>
        )}
        {moversSelection && (
          <MoversPanel
            providers={active}
            regionsByProvider={regionsByProvider}
            selection={moversSelection}
            onChange={changeMovers}
            onReset={() => patchSection("trends.movers", null)}
          />
        )}
      </section>
    </div>
  );
}
