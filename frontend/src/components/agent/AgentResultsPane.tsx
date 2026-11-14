/**
 * 024 (US6, FR-013, FR-019, FR-020, contracts/results-pane-ui.md): one comparison result as an
 * app-drawn table, with stepping through the session's results, Download CSV and Close. Every
 * figure is the result's own (the pricing engine's); nothing here goes through the model.
 */
import { ChevronLeft, ChevronRight, Download, X } from "lucide-react";
import { useState } from "react";

import type { AgentResult, AgentResultCell } from "../../api/client";
import {
  DURATION_TEXT,
  PROVIDER_NAMES,
  QUALITY_TEXT,
  STATUS_TEXT,
  downloadResultCsv,
  formatMoney,
  formatPercent,
  sideNames,
  termText,
} from "../../lib/agentResults";
import { Button } from "../ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

export type AgentResultsPaneProps = {
  results: AgentResult[];
  selectedId: string;
  onStep: (delta: -1 | 1) => void;
  onClose: () => void;
  download?: (id: string) => Promise<void>;
};

function signed(text: string): string {
  return text && !text.startsWith("-") && text !== "$0.00" ? `+${text}` : text;
}

function QualityBadge({ cell }: { cell: AgentResultCell }) {
  const shown = cell.shown_quality ?? cell.quality;
  if (!shown) return null;
  const details = [
    ...(cell.differences ?? []),
    ...(cell.quality_reason ? [`Lowered by the agent: ${cell.quality_reason}`] : []),
  ];
  const badge = (
    <span className="rounded border border-border px-1 py-0.5 text-[10px] whitespace-nowrap">
      {QUALITY_TEXT[shown] ?? shown}
    </span>
  );
  if (details.length === 0) return badge;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="focus-ring rounded"
          aria-label={`${QUALITY_TEXT[shown] ?? shown} match: ${details.join("; ")}`}
        >
          {badge}
        </button>
      </TooltipTrigger>
      <TooltipContent>
        <ul className="max-w-64 list-disc pl-4 text-xs">
          {details.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
      </TooltipContent>
    </Tooltip>
  );
}

function StatusText({ cell }: { cell: AgentResultCell }) {
  const text = STATUS_TEXT[cell.status ?? ""] ?? cell.status;
  if (!cell.reason) return <span className="text-muted-foreground italic">{text}</span>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="focus-ring rounded text-muted-foreground italic"
          aria-label={`${text}: ${cell.reason}`}
        >
          {text}
        </button>
      </TooltipTrigger>
      <TooltipContent>{cell.reason}</TooltipContent>
    </Tooltip>
  );
}

export function AgentResultsPane({
  results,
  selectedId,
  onStep,
  onClose,
  download = downloadResultCsv,
}: AgentResultsPaneProps) {
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const index = results.findIndex((r) => r.id === selectedId);
  const result = results[index];
  if (!result) return null;
  const names = sideNames(result.sides);
  const reference = result.basis.reference_side;
  const isArchitecture = result.basis.question_kind === "architecture";
  const targets = result.sides.filter((s) => s.id !== reference);
  const partial = Object.values(result.totals).some((t) => t.partial);

  async function onDownload() {
    setFailed(false);
    setBusy(true);
    try {
      await download(result.id);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Results" className="flex h-full min-h-0 flex-col text-xs">
      <header className="flex shrink-0 items-center gap-1 border-b border-border px-2 py-1">
        <h3 className="sr-only">Results</h3>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          aria-label="Previous result"
          disabled={index <= 0}
          onClick={() => onStep(-1)}
        >
          <ChevronLeft />
        </Button>
        <span aria-live="polite">
          Result {index + 1} of {results.length}
        </span>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          aria-label="Next result"
          disabled={index >= results.length - 1}
          onClick={() => onStep(1)}
        >
          <ChevronRight />
        </Button>
        <div className="ml-auto flex items-center gap-1">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => void onDownload()}
          >
            <Download /> Download CSV
          </Button>
          <Button type="button" size="sm" variant="ghost" aria-label="Close results" onClick={onClose}>
            <X />
          </Button>
        </div>
      </header>
      {failed && (
        <p role="alert" className="shrink-0 border-b border-border px-2 py-1 text-destructive">
          Couldn&apos;t download the result.
        </p>
      )}
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="space-y-0.5 px-2 py-1.5">
          <p className="font-medium text-foreground">{result.title}</p>
          {result.sides.map((side) => {
            const snapshot = result.snapshots[side.provider];
            return (
              <p key={side.id} className="text-muted-foreground">
                {names[side.id]}: {side.region || "no region"}
                {side.region_guessed ? " (guessed)" : ""} · {termText(side.term, side.purchase_option)}
                {snapshot ? ` · prices from ${snapshot.date}` : ""}
                {side.id === reference ? " · reference" : ""}
              </p>
            );
          })}
          <p className="text-muted-foreground">
            {DURATION_TEXT[result.basis.duration] ?? result.basis.duration} · USD ·{" "}
            {result.basis.usage}
          </p>
          {(result.basis.assumptions ?? []).length > 0 && (
            <p className="text-muted-foreground">
              Assumptions: {(result.basis.assumptions ?? []).join("; ")}
            </p>
          )}
        </div>
        <table className="w-full border-collapse">
          <caption className="sr-only">{result.title}</caption>
          <thead className="sticky top-0 bg-background">
            <tr className="border-y border-border text-left">
              <th scope="col" className="px-2 py-1 font-medium">
                Service
              </th>
              {result.sides.map((side) => (
                <th key={side.id} scope="col" className="px-2 py-1 font-medium">
                  {names[side.id]}
                </th>
              ))}
              {targets.map((side) => (
                <th key={`d-${side.id}`} scope="col" className="px-2 py-1 text-right font-medium">
                  {names[side.id]} difference
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, i) => (
              <tr key={`${row.label}-${i}`} className="border-b border-border align-top">
                <th scope="row" className="px-2 py-1 text-left font-normal">
                  {row.label}
                  {isArchitecture && row.where && (
                    <span className="block text-muted-foreground">{row.where}</span>
                  )}
                </th>
                {result.sides.map((side) => {
                  const cell = row.cells[side.id];
                  return (
                    <td key={side.id} className="px-2 py-1">
                      {!cell ? null : cell.status === "ok" ? (
                        <>
                          <span className="block text-right font-medium tabular-nums">
                            {formatMoney(cell.amount)}
                          </span>
                          <span className="block text-muted-foreground">{cell.product}</span>
                          {side.id !== reference && <QualityBadge cell={cell} />}
                        </>
                      ) : (
                        <>
                          <StatusText cell={cell} />
                          {cell.product && (
                            <span className="block text-muted-foreground">{cell.product}</span>
                          )}
                        </>
                      )}
                    </td>
                  );
                })}
                {targets.map((side) => {
                  const cell = row.cells[side.id];
                  return (
                    <td key={`d-${side.id}`} className="px-2 py-1 text-right tabular-nums">
                      {cell?.diff != null ? (
                        <>
                          {signed(formatMoney(cell.diff))}
                          <span className="block text-muted-foreground">
                            {formatPercent(cell.diff_pct)}
                          </span>
                        </>
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-b border-border font-medium">
              <th scope="row" className="px-2 py-1 text-left">
                {partial ? "Total (partial)" : "Total"}
              </th>
              {result.sides.map((side) => (
                <td key={side.id} className="px-2 py-1 text-right tabular-nums">
                  {formatMoney(result.totals[side.id]?.amount)}
                </td>
              ))}
              {targets.map((side) => {
                const total = result.totals[side.id];
                return (
                  <td key={`d-${side.id}`} className="px-2 py-1 text-right tabular-nums">
                    {total?.diff != null && (
                      <>
                        {signed(formatMoney(total.diff))}
                        <span className="block text-muted-foreground">
                          {formatPercent(total.diff_pct)}
                        </span>
                      </>
                    )}
                  </td>
                );
              })}
            </tr>
          </tfoot>
        </table>
        {(result.not_compared ?? []).length > 0 && (
          <div className="px-2 py-1.5 text-muted-foreground">
            <p className="font-medium text-foreground">Not compared:</p>
            <ul className="list-disc pl-4">
              {(result.not_compared ?? []).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
        <p className="px-2 pb-2 text-[10px] text-muted-foreground">
          Providers: {result.sides.map((s) => PROVIDER_NAMES[s.provider]).join(", ")}. Prices
          from the app&apos;s pricing data; nothing estimated.
        </p>
      </div>
    </section>
  );
}
