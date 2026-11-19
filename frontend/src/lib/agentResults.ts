/**
 * 024-agent-pricing-questions (US6, FR-018–FR-021, contracts/results-pane-ui.md): the Agent
 * tab's Results pane — which result is shown and whether the pane is open, the figures as the
 * pane shows them, the saved conversation/results split, and the CSV download.
 *
 * Amounts arrive as unrounded decimal strings. They're rounded here on the decimal digits
 * (half-up, like the server's `round_cents`), never through floating point, so the pane always
 * shows what the downloaded CSV contains (SC-008).
 */
import {
  API_BASE,
  apiHeaders,
  type AgentResult,
  type WorkspacePreferences,
} from "../api/client";
import { type PreferencesStore, preferencesStore } from "./preferences";

// --- Pane state ---------------------------------------------------------------------------------

export type ResultsPaneState = { open: boolean; selectedId: string | null };

export type ResultsPaneAction =
  /** The session's results were loaded (a reopened session opens on its latest result). */
  | { type: "loaded"; ids: string[] }
  /** A result arrived in the stream: open the pane on it. */
  | { type: "arrived"; id: string }
  | { type: "show"; id: string }
  | { type: "step"; delta: -1 | 1; ids: string[] }
  | { type: "close" }
  | { type: "reset" };

export const CLOSED: ResultsPaneState = { open: false, selectedId: null };

export function resultsPane(state: ResultsPaneState, action: ResultsPaneAction): ResultsPaneState {
  switch (action.type) {
    case "loaded":
      if (action.ids.length === 0) return CLOSED;
      if (state.selectedId && action.ids.includes(state.selectedId)) return state;
      return { open: true, selectedId: action.ids[action.ids.length - 1] };
    case "arrived":
    case "show":
      return { open: true, selectedId: action.id };
    case "step": {
      const at = state.selectedId ? action.ids.indexOf(state.selectedId) : -1;
      const next = at + action.delta;
      if (at < 0 || next < 0 || next >= action.ids.length) return state;
      return { ...state, selectedId: action.ids[next] };
    }
    case "close":
      return { ...state, open: false };
    case "reset":
      return CLOSED;
  }
}

// --- Figures ------------------------------------------------------------------------------------

/** "0E-13" → "0.0000000000000", "1.5E+3" → "1500": exponent form as a plain decimal, exactly
 * (no float conversion). Anything else is returned unchanged. */
function expandExponent(value: string): string {
  const match = /^([+-]?)(\d*)(?:\.(\d*))?[eE]([+-]?\d+)$/.exec(value.trim());
  if (!match) return value;
  const [, sign, whole = "", fraction = "", exp] = match;
  const digits = whole + fraction;
  const point = whole.length + Number(exp);
  let out: string;
  if (point <= 0) out = `0.${"0".repeat(-point)}${digits}`;
  else if (point >= digits.length) out = digits + "0".repeat(point - digits.length);
  else out = `${digits.slice(0, point)}.${digits.slice(point)}`;
  return sign + (out.startsWith(".") ? `0${out}` : out);
}

/** `value` (a decimal string) rounded half-up to `places`, as a plain decimal string. */
export function roundDecimal(value: string, places: number): string {
  const match = /^([+-]?)(\d*)(?:\.(\d*))?$/.exec(expandExponent(value.trim()));
  if (!match) return value;
  const negative = match[1] === "-";
  const whole = match[2] || "0";
  const fraction = (match[3] ?? "").padEnd(places + 1, "0");
  const kept = fraction.slice(0, places);
  const roundUp = Number(fraction[places]) >= 5;
  let digits = (whole + kept).replace(/^0+(?=\d)/, "");
  if (roundUp) {
    const chars = digits.split("");
    let i = chars.length - 1;
    for (; i >= 0; i--) {
      if (chars[i] === "9") {
        chars[i] = "0";
      } else {
        chars[i] = String(Number(chars[i]) + 1);
        break;
      }
    }
    digits = (i < 0 ? "1" : "") + chars.join("");
  }
  digits = digits.padStart(places + 1, "0");
  const intPart = digits.slice(0, digits.length - places) || "0";
  const fracPart = places ? digits.slice(digits.length - places) : "";
  const isZero = /^0*$/.test(intPart + fracPart);
  const sign = negative && !isZero ? "-" : "";
  return places ? `${sign}${intPart}.${fracPart}` : `${sign}${intPart}`;
}

function group(intPart: string): string {
  return intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** "$1,234.56" / "-$12.00" from an unrounded decimal string; "" for null. */
export function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  const rounded = roundDecimal(String(value), 2);
  const negative = rounded.startsWith("-");
  const [intPart, frac] = rounded.replace("-", "").split(".");
  return `${negative ? "-" : ""}$${group(intPart)}.${frac}`;
}

/** "+12.3%" / "-4.0%" / "0.0%" from an unrounded percentage; "" for null. */
export function formatPercent(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  const rounded = roundDecimal(String(value), 1);
  const positive = !rounded.startsWith("-") && !/^0\.0$/.test(rounded);
  return `${positive ? "+" : ""}${rounded}%`;
}

export const QUALITY_TEXT: Record<string, string> = {
  exact: "Exact",
  close: "Close",
  partial: "Partial",
  no_equivalent: "No equivalent",
};

export const STATUS_TEXT: Record<string, string> = {
  unavailable: "Unavailable",
  unmatched: "No equivalent",
  unconvertible: "Can't convert usage",
};

export const PROVIDER_NAMES: Record<string, string> = { aws: "AWS", azure: "Azure", gcp: "GCP" };

const TERM_TEXT: Record<string, string> = {
  on_demand: "on demand",
  reserved_1yr: "reserved 1 year",
  reserved_3yr: "reserved 3 years",
  savings_plan_1yr: "savings plan 1 year",
  savings_plan_3yr: "savings plan 3 years",
  commitment_1yr: "committed use 1 year",
  commitment_3yr: "committed use 3 years",
  as_saved: "as in the architecture",
};

export function termText(term: string, purchaseOption?: string | null): string {
  const text = TERM_TEXT[term] ?? term;
  return purchaseOption ? `${text}, ${purchaseOption.replace(/_/g, " ")}` : text;
}

export const DURATION_TEXT: Record<string, string> = {
  "1_day": "1 day",
  "1_month": "1 month (31 days)",
  "1_year": "1 year (365 days)",
};

/** Column-group names: the provider, plus the region when a provider appears twice. */
export function sideNames(sides: AgentResult["sides"]): Record<string, string> {
  const counts: Record<string, number> = {};
  for (const s of sides) counts[s.provider] = (counts[s.provider] ?? 0) + 1;
  return Object.fromEntries(
    sides.map((s) => [
      s.id,
      counts[s.provider] > 1
        ? `${PROVIDER_NAMES[s.provider]} ${s.region}`
        : PROVIDER_NAMES[s.provider],
    ]),
  );
}

// --- The saved split ----------------------------------------------------------------------------

export const RESULTS_SPLIT = { min: 0.3, max: 0.75, default: 0.45 } as const;

export function clampSplit(split: number): number {
  return Math.min(RESULTS_SPLIT.max, Math.max(RESULTS_SPLIT.min, split));
}

export function readResultsSplit(workspace: WorkspacePreferences | null | undefined): number {
  const split = workspace?.agent_results?.split;
  return typeof split === "number" ? clampSplit(split) : RESULTS_SPLIT.default;
}

/** Saves the split. A PATCH replaces the whole workspace section, so the rest is sent back. */
export function writeResultsSplit(split: number, store: PreferencesStore = preferencesStore): void {
  const rounded = Math.round(clampSplit(split) * 100) / 100;
  store.patchSection("workspace", {
    ...(store.current.workspace ?? {}),
    agent_results: { split: rounded },
  });
}

// --- Download -----------------------------------------------------------------------------------

function filenameOf(disposition: string | null, fallback: string): string {
  const match = disposition ? /filename="([^"]+)"/.exec(disposition) : null;
  return match ? match[1] : fallback;
}

/** Fetches the result's CSV with the auth header and saves it through the browser. */
export async function downloadResultCsv(resultId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/agent/session/results/${resultId}/csv`, {
    headers: apiHeaders(),
  });
  if (!response.ok) throw new Error(`download failed: ${response.status}`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filenameOf(response.headers.get("Content-Disposition"), "comparison.csv");
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
