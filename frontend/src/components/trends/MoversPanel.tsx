import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, RotateCcw } from "lucide-react";

import {
  type Mover,
  type Provider,
  type ProviderCode,
  type Region,
  type TrendsCategory,
  api,
} from "../../api/client";
import { regionLabel } from "../../lib/providerPricing";
import {
  CATEGORY_LABELS,
  MOVERS_PERIODS,
  type MoversPeriod,
  type MoversSelection,
  formatChangePct,
  moversNote,
} from "../../lib/trends";
import { ErrorMessage } from "../ErrorMessage";
import { Button } from "../ui/button";

interface Props {
  /** Active providers only. */
  providers: Provider[];
  regionsByProvider: Partial<Record<ProviderCode, Region[]>>;
  selection: MoversSelection;
  onChange: (selection: MoversSelection) => void;
  /** Restores the first available provider, all categories, all regions, 52 weeks (FR-020). */
  onReset: () => void;
}

const selectClassName =
  "rounded-md border border-input bg-background px-1.5 py-1 text-2xs font-normal";

function MoverItem({ mover, up }: { mover: Mover; up: boolean }) {
  const Arrow = up ? ArrowUp : ArrowDown;
  return (
    <li className="flex items-start gap-2 rounded border border-border px-2 py-1.5">
      <span className="flex w-16 shrink-0 items-center gap-0.5 font-medium tabular-nums">
        <Arrow aria-hidden className={`size-3 ${up ? "text-chart-up" : "text-chart-down"}`} />
        {formatChangePct(mover.change_pct)}
      </span>
      <div className="min-w-0 break-words">
        <p>
          <span className="font-medium">{mover.service_name}</span> — {mover.description}
        </p>
        <p className="text-muted-foreground">
          {mover.region} · <span className="tabular-nums">${mover.start_price}</span> →{" "}
          <span className="tabular-nums">${mover.end_price}</span>
          {mover.unit ? ` per ${mover.unit}` : ""}
        </p>
        {mover.tier_note && <p className="text-muted-foreground italic">{mover.tier_note}</p>}
      </div>
    </li>
  );
}

function MoverList({ title, movers, up }: { title: string; movers: Mover[]; up: boolean }) {
  return (
    <section aria-label={title} className="flex flex-col gap-1">
      <h3 className="text-2xs font-semibold">{title}</h3>
      {movers.length === 0 ? (
        <p className="text-muted-foreground">None in this period.</p>
      ) : (
        <ol className="flex flex-col gap-1">
          {movers.map((m, i) => (
            <MoverItem key={`${i}/${m.region}/${m.description}`} mover={m} up={up} />
          ))}
        </ol>
      )}
    </section>
  );
}

/**
 * Biggest movers (019, US3, FR-016 to FR-020): the 3 largest % on-demand price increases and
 * decreases for one provider, category, regions (none ticked means all) and period. Prices are
 * shown exactly as published; a tiered price is compared on its first non-zero tier, which the
 * entry says.
 */
export function MoversPanel({ providers, regionsByProvider, selection, onChange, onReset }: Props) {
  const movers = useQuery({
    queryKey: ["trends", "movers", selection],
    queryFn: () => api.getTrendMovers(selection),
    refetchInterval: (query) => (query.state.data?.status === "building" ? 15_000 : false),
  });
  const regions = regionsByProvider[selection.provider] ?? [];

  function toggleRegion(region: string) {
    onChange({
      ...selection,
      regions: selection.regions.includes(region)
        ? selection.regions.filter((r) => r !== region)
        : [...selection.regions, region].sort(),
    });
  }

  const note = movers.data ? moversNote(movers.data) : null;

  return (
    <div className="flex min-h-0 flex-col gap-3 text-2xs">
      <div className="flex flex-wrap items-end gap-3" aria-label="Movers selection">
        <label className="flex flex-col gap-0.5 font-medium">
          Provider
          <select
            className={selectClassName}
            value={selection.provider}
            onChange={(e) =>
              onChange({ ...selection, provider: e.target.value as ProviderCode, regions: [] })
            }
          >
            {providers.map((p) => (
              <option key={p.code} value={p.code}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-0.5 font-medium">
          Category
          <select
            className={selectClassName}
            value={selection.category}
            onChange={(e) => onChange({ ...selection, category: e.target.value as TrendsCategory })}
          >
            {(Object.keys(CATEGORY_LABELS) as TrendsCategory[]).map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABELS[c]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-0.5 font-medium">
          Period
          <select
            className={selectClassName}
            value={selection.period_weeks}
            onChange={(e) =>
              onChange({ ...selection, period_weeks: Number(e.target.value) as MoversPeriod })
            }
          >
            {MOVERS_PERIODS.map((p) => (
              <option key={p.weeks} value={p.weeks}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <Button variant="outline" size="sm" onClick={onReset}>
          <RotateCcw /> Reset
        </Button>
      </div>
      <fieldset className="flex flex-col gap-0.5">
        <legend className="font-medium">
          Regions{" "}
          <span className="font-normal text-muted-foreground">
            ({selection.regions.length === 0 ? "all" : `${selection.regions.length} selected`})
          </span>
        </legend>
        <div
          role="group"
          aria-label="Movers regions"
          className="flex max-h-24 flex-col gap-0.5 overflow-auto"
        >
          {regions.map((r) => (
            <label key={r.code} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={selection.regions.includes(r.code)}
                onChange={() => toggleRegion(r.code)}
              />
              {regionLabel(r)}
            </label>
          ))}
        </div>
      </fieldset>

      {movers.isError && (
        <ErrorMessage message={movers.error.message} onRetry={() => movers.refetch()} />
      )}
      {movers.isLoading && <p className="text-muted-foreground">Loading…</p>}
      {movers.data && (
        <>
          {note && <p className="text-muted-foreground">{note}</p>}
          {movers.data.message ? (
            <p>{movers.data.message}</p>
          ) : (
            movers.data.from_snapshot && (
              <>
                <MoverList title="Largest increases" movers={movers.data.increases} up />
                <MoverList title="Largest decreases" movers={movers.data.decreases} up={false} />
              </>
            )
          )}
        </>
      )}
    </div>
  );
}
