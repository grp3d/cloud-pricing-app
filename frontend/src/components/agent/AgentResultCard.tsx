/**
 * 024 (FR-019, contracts/results-pane-ui.md "Card in the conversation"): the card under an
 * answer that names its result; selecting it shows that result in the Results pane.
 */
import type { AgentResult } from "../../api/client";

export function AgentResultCard({
  result,
  current,
  onShow,
}: {
  result: AgentResult;
  current: boolean;
  onShow: (id: string) => void;
}) {
  return (
    <button
      type="button"
      aria-label={`Show result: ${result.title}`}
      aria-current={current ? "true" : undefined}
      className={`focus-ring mt-1 flex w-full items-start gap-2 rounded-md border px-2 py-1.5 text-left ${
        current ? "border-primary bg-primary/5" : "border-border bg-background hover:bg-muted"
      }`}
      onClick={() => onShow(result.id)}
    >
      <span aria-hidden className="mt-0.5">
        ▦
      </span>
      <span className="min-w-0">
        <span className="block truncate font-medium">{result.title}</span>
        <span className="block text-muted-foreground">{result.summary}</span>
      </span>
    </button>
  );
}
