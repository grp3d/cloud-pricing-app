/**
 * 026 (contracts/translation-ui.md, US2, FR-007): a translation's mapping table, one row per
 * source service, and the cost difference: both totals, the difference on the matched services,
 * what was left out, the main drivers and both pricing snapshots. Figures are the pricing
 * engine's, rounded as the Results pane does.
 */
import type { AgentProposal } from "../../api/client";
import { DURATION_TEXT, formatMoney, formatPercent } from "../../lib/agentResults";
import { PROVIDER_TEXT } from "../../lib/agentProposals";

type Translation = NonNullable<AgentProposal["translation"]>;
type Row = Translation["rows"][number];

const QUALITY_TEXT: Record<string, string> = { exact: "Exact", close: "Close", partial: "Partial" };
const ORIGIN_TEXT: Record<string, string> = {
  seeded: "Seeded",
  automatic: "Automatic",
  chosen_by_user: "Chosen by you",
};
const STATUS_TEXT: Record<string, string> = {
  no_equivalent: "No equivalent",
  partial_only: "Only a partial match: ask the agent to use it",
  not_sold_in_region: "No match in this region",
  unpriceable: "Can't be priced",
};

function signed(text: string): string {
  return text && !text.startsWith("-") && text !== "$0.00" ? `+${text}` : text;
}

function money(value: string | null | undefined): string {
  return value == null ? "—" : formatMoney(value);
}

function others(count: number): string | null {
  if (!count) return null;
  return `${count} other ${count === 1 ? "option" : "options"}`;
}

function MappingRow({ row }: { row: Row }) {
  const reason =
    row.match == null
      ? `${STATUS_TEXT[row.status] ?? row.status}${row.reason && row.status !== "partial_only" ? `: ${row.reason}` : ""}`
      : null;
  return (
    <tr className="border-b border-border align-top">
      <th scope="row" className="px-1 py-1 text-left font-normal">
        <span className="block">{row.source.label}</span>
        <span className="block text-muted-foreground">{row.where}</span>
      </th>
      <td className="px-1 py-1">
        {row.match ? (
          <>
            <span className="block">{row.match.label}</span>
            {row.match.size && (
              <span className="block text-muted-foreground">{row.match.size}</span>
            )}
          </>
        ) : (
          <span className="text-muted-foreground">{reason}</span>
        )}
      </td>
      <td className="px-1 py-1">{row.quality ? QUALITY_TEXT[row.quality] : ""}</td>
      <td className="px-1 py-1">{row.origin ? ORIGIN_TEXT[row.origin] : ""}</td>
      <td className="px-1 py-1">
        {row.origin === "chosen_by_user" && (
          <span className="block">Partial match you chose; not checked as equivalent.</span>
        )}
        {row.differences.map((d) => (
          <span key={d} className="block">
            {d}
          </span>
        ))}
        {row.assumptions.map((a) => (
          <span key={a} className="block text-muted-foreground">
            {a}
          </span>
        ))}
        {others(row.alternatives ?? 0) && (
          <span className="block text-muted-foreground">{others(row.alternatives ?? 0)}</span>
        )}
        {row.match && row.status === "unpriceable" && row.reason && (
          <span className="block text-muted-foreground">{row.reason}</span>
        )}
      </td>
      <td className="px-1 py-1 text-right tabular-nums">{money(row.source.amount)}</td>
      <td className="px-1 py-1 text-right tabular-nums">
        {row.match ? money(row.match.amount) : "—"}
      </td>
    </tr>
  );
}

export function TranslationTable({ translation }: { translation: Translation }) {
  const s = translation.summary;
  const source = PROVIDER_TEXT[translation.source_provider] ?? translation.source_provider;
  const target = PROVIDER_TEXT[translation.target_provider] ?? translation.target_provider;
  const compared = s.compared;
  const snapshots = Object.entries(s.snapshots)
    .map(([p, d]) => `${PROVIDER_TEXT[p] ?? p} ${d}`)
    .join(", ");
  return (
    <div className="space-y-2">
      <div>
        {translation.regions.map((r) => (
          <p key={r.source}>{`${r.source} → ${r.target}${r.guessed ? " (a guess)" : ""}`}</p>
        ))}
        <p className="text-muted-foreground">
          {`Pricing: ${translation.term.used}${translation.term.why ? ` — ${translation.term.why}` : ""}`}
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse" aria-label="Mapping">
          <thead>
            <tr className="border-y border-border text-left">
              <th scope="col" className="px-1 py-1 font-medium">
                Original
              </th>
              <th scope="col" className="px-1 py-1 font-medium">
                Match
              </th>
              <th scope="col" className="px-1 py-1 font-medium">
                Quality
              </th>
              <th scope="col" className="px-1 py-1 font-medium">
                From
              </th>
              <th scope="col" className="px-1 py-1 font-medium">
                Differences
              </th>
              <th scope="col" className="px-1 py-1 text-right font-medium">
                {source}
              </th>
              <th scope="col" className="px-1 py-1 text-right font-medium">
                {target}
              </th>
            </tr>
          </thead>
          <tbody>
            {translation.rows.map((row, i) => (
              <MappingRow key={`${row.where}-${row.source.label}-${i}`} row={row} />
            ))}
          </tbody>
        </table>
      </div>

      <section aria-label="Cost difference" className="space-y-1">
        <p className="font-medium">Cost difference</p>
        <ul className="pl-0">
          <li className="flex justify-between tabular-nums">
            <span>{`${source} total${s.original_total.partial ? " (partial)" : ""}`}</span>
            <span>{money(s.original_total.amount)}</span>
          </li>
          <li className="flex justify-between tabular-nums">
            <span>{`${target} total${s.translation_total.partial ? " (partial)" : ""}`}</span>
            <span>{money(s.translation_total.amount)}</span>
          </li>
        </ul>
        {compared.diff != null && (
          <p className="font-medium">
            {`On the ${compared.rows} matched services: ${signed(formatMoney(compared.diff))}${
              compared.diff_pct != null ? ` (${formatPercent(compared.diff_pct)})` : ""
            }`}
          </p>
        )}
        {s.left_out.length > 0 && (
          <div>
            <p>Left out of the difference</p>
            <ul className="list-disc pl-4">
              {s.left_out.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </div>
        )}
        {s.drivers.length > 0 && (
          <div>
            <p>Main drivers</p>
            <ul className="pl-0">
              {s.drivers.map((d) => (
                <li key={`${d.where}-${d.label}`} className="flex justify-between tabular-nums">
                  <span>{`${d.label} (${d.where})`}</span>
                  <span>{signed(formatMoney(d.diff))}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <p className="text-[10px] text-muted-foreground">
          {`${DURATION_TEXT[s.duration] ?? s.duration} · USD · prices from ${snapshots}. Nothing is created until you accept.`}
        </p>
      </section>
    </div>
  );
}
