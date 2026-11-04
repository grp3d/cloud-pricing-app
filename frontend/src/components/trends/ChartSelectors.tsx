import { RotateCcw } from "lucide-react";

import type { Provider, ProviderCode, Region, TrendsCategory } from "../../api/client";
import { regionLabel } from "../../lib/providerPricing";
import { CATEGORY_LABELS, type ChartSelection } from "../../lib/trends";
import { Button } from "../ui/button";

interface Props {
  /** Active providers only (FR-011). */
  providers: Provider[];
  regionsByProvider: Partial<Record<ProviderCode, Region[]>>;
  selection: ChartSelection;
  onChange: (selection: ChartSelection) => void;
  /** Restores all providers, all regions, all categories (FR-020). */
  onReset: () => void;
}

/** The charts section's selectors (019, FR-011, FR-015a, FR-020): providers with their regions
 * listed under each (none ticked means all regions), one category, and Reset. */
export function ChartSelectors({
  providers,
  regionsByProvider,
  selection,
  onChange,
  onReset,
}: Props) {
  const chosen = new Map(selection.providers.map((p) => [p.provider, p.regions]));

  function toggleProvider(code: ProviderCode) {
    const next = chosen.has(code)
      ? selection.providers.filter((p) => p.provider !== code)
      : [...selection.providers, { provider: code, regions: [] }];
    onChange({ ...selection, providers: next });
  }

  function toggleRegion(code: ProviderCode, region: string) {
    onChange({
      ...selection,
      providers: selection.providers.map((p) =>
        p.provider !== code
          ? p
          : {
              ...p,
              regions: p.regions.includes(region)
                ? p.regions.filter((r) => r !== region)
                : [...p.regions, region].sort(),
            },
      ),
    });
  }

  return (
    <div className="flex flex-wrap items-start gap-4 text-2xs" aria-label="Chart selection">
      {providers.map((p) => {
        const code = p.code as ProviderCode;
        const regions = chosen.get(code);
        return (
          <fieldset key={code} className="flex flex-col gap-0.5">
            <label className="flex items-center gap-1 font-medium">
              <input
                type="checkbox"
                checked={regions !== undefined}
                onChange={() => toggleProvider(code)}
              />
              {p.name}
            </label>
            {regions !== undefined && (
              <div
                role="group"
                aria-label={`${p.name} regions`}
                className="flex max-h-28 flex-col gap-0.5 overflow-auto pl-4"
              >
                <span className="text-muted-foreground">
                  {regions.length === 0 ? "All regions" : `${regions.length} selected`}
                </span>
                {(regionsByProvider[code] ?? []).map((r) => (
                  <label key={r.code} className="flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={regions.includes(r.code)}
                      onChange={() => toggleRegion(code, r.code)}
                    />
                    {regionLabel(r)}
                  </label>
                ))}
              </div>
            )}
          </fieldset>
        );
      })}
      <label className="flex flex-col gap-0.5 font-medium">
        Category
        <select
          className="rounded border border-border bg-background px-1.5 py-1 text-2xs font-normal"
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
      <Button variant="outline" size="sm" onClick={onReset} className="self-end">
        <RotateCcw /> Reset
      </Button>
    </div>
  );
}
