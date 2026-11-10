import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { SkusChangedPoint, TrendSeries } from "../../api/client";
import { seriesTitle, statusNote } from "../../lib/trends";

/**
 * SKUs Changed (019, FR-012, FR-013, R14): one up/down pair per provider, as small multiples —
 * each provider its own chart on the same kind of axis, so identity is the chart title, not a
 * color. Up (price rose) is drawn above zero in `--chart-up`, down below it in `--chart-down`:
 * position carries the direction as well as color. A week with nothing compared is "no data"
 * (no bar), never 0; a week after a missing one is marked with a dashed line. Every chart has a
 * table view with the same numbers.
 */

const TIER_NOTE = "Tiered prices are compared on their first non-zero tier.";

function pct(value: number | null | undefined): string {
  return value == null ? "" : ` (${value.toLocaleString("en-US", { maximumFractionDigits: 4 })}%)`;
}

function count(value: number | null | undefined): string {
  return value == null ? "No data" : value.toLocaleString("en-US");
}

function PointTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: SkusChangedPoint }[];
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded border border-border bg-background px-2 py-1.5 text-2xs text-foreground shadow-sm">
      <p className="font-semibold">Week of {p.week}</p>
      <p className="text-muted-foreground">
        {p.from_snapshot} → {p.to_snapshot}
      </p>
      {p.compared == null ? (
        <p>No data: no SKUs were compared this week.</p>
      ) : (
        <>
          <p>
            <span className="mr-1 inline-block size-2 rounded-sm bg-chart-up" />
            Up: {count(p.increased)}
            {pct(p.increased_pct)}
          </p>
          <p>
            <span className="mr-1 inline-block size-2 rounded-sm bg-chart-down" />
            Down: {count(p.decreased)}
            {pct(p.decreased_pct)}
          </p>
          <p className="text-muted-foreground">
            Compared {count(p.compared)} · left out {count(p.excluded)}
          </p>
        </>
      )}
      {p.gap && <p className="text-muted-foreground">A week is missing before this one.</p>}
      <p className="text-muted-foreground">{TIER_NOTE}</p>
    </div>
  );
}

function SeriesChart({ series }: { series: TrendSeries }) {
  const data = series.points.map((p) => ({
    ...p,
    up: p.increased,
    down: p.decreased == null ? null : -p.decreased,
  }));
  return (
    <div className="h-40 w-full" aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} stackOffset="sign" margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--color-border)" strokeOpacity={0.6} />
          <XAxis
            dataKey="week"
            tick={{ fontSize: 10, fill: "var(--color-muted-foreground)" }}
            tickLine={false}
            axisLine={false}
            minTickGap={16}
          />
          <YAxis
            allowDecimals={false}
            width={36}
            tick={{ fontSize: 10, fill: "var(--color-muted-foreground)" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => Math.abs(v).toLocaleString("en-US")}
          />
          <ReferenceLine y={0} stroke="var(--color-muted-foreground)" strokeOpacity={0.6} />
          {data
            .filter((p) => p.gap)
            .map((p) => (
              <ReferenceLine
                key={`gap-${p.week}`}
                x={p.week}
                stroke="var(--color-muted-foreground)"
                strokeDasharray="3 3"
              />
            ))}
          <Tooltip
            content={<PointTooltip />}
            cursor={{ fill: "var(--color-muted)", fillOpacity: 0.5 }}
          />
          <Bar
            dataKey="up"
            stackId="direction"
            fill="var(--color-chart-up)"
            radius={[4, 4, 0, 0]}
            maxBarSize={14}
            isAnimationActive={false}
          />
          <Bar
            dataKey="down"
            stackId="direction"
            fill="var(--color-chart-down)"
            radius={[4, 4, 0, 0]}
            maxBarSize={14}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function SeriesTable({ series }: { series: TrendSeries }) {
  return (
    <details className="text-2xs">
      <summary className="cursor-pointer text-muted-foreground">Table</summary>
      <table aria-label={`${seriesTitle(series)} weekly changes`} className="mt-1 w-full">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="py-0.5">Week</th>
            <th className="py-0.5 text-right">Up</th>
            <th className="py-0.5 text-right">Down</th>
            <th className="py-0.5 text-right">Compared</th>
            <th className="py-0.5 text-right">Left out</th>
          </tr>
        </thead>
        <tbody>
          {series.points.map((p) => (
            <tr key={p.week} className="border-t border-border">
              <td className="py-0.5">
                {p.week}
                {p.gap ? " (after a gap)" : ""}
              </td>
              <td className="py-0.5 text-right tabular-nums">{count(p.increased)}</td>
              <td className="py-0.5 text-right tabular-nums">{count(p.decreased)}</td>
              <td className="py-0.5 text-right tabular-nums">{count(p.compared)}</td>
              <td className="py-0.5 text-right tabular-nums">{count(p.excluded)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

export function TrendsChartPanel({ series }: { series: TrendSeries[] }) {
  if (series.length === 0) {
    return <p className="text-2xs text-muted-foreground">Select at least one provider.</p>;
  }
  return (
    <div className="flex flex-col gap-3">
      {/* Two series per chart (up, down), so a legend is always present. */}
      <div className="flex items-center gap-3 text-2xs text-muted-foreground" aria-label="Legend">
        <span className="flex items-center gap-1">
          <span className="inline-block size-2.5 rounded-sm bg-chart-up" /> Up: SKUs whose price
          rose
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block size-2.5 rounded-sm bg-chart-down" /> Down: SKUs whose price
          fell
        </span>
      </div>
      {series.map((s) => {
        const note = statusNote(s);
        return (
          <section
            key={s.provider}
            aria-label={seriesTitle(s)}
            className="flex flex-col gap-1 rounded border border-border p-2"
          >
            <h3 className="text-2xs font-semibold">{seriesTitle(s)}</h3>
            {note && <p className="text-2xs text-muted-foreground">{note}</p>}
            {s.points.length > 0 && (
              <>
                <SeriesChart series={s} />
                <SeriesTable series={s} />
              </>
            )}
          </section>
        );
      })}
    </div>
  );
}
