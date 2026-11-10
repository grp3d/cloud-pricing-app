/**
 * Workspace settings saved in the browser by earlier versions (008 column widths, 009 collapsed
 * columns), read only to move them to the user's account once (019, FR-024). Never written.
 * A missing key, malformed JSON or an invalid entry never throws: that value is just skipped.
 */
import type { WorkspacePreferences } from "../api/client";

export type ColumnKey = "col1" | "col2" | "col3" | "col4";

export const WIDTHS_STORAGE_KEY = "cloud-pricing-column-widths";
export const COLLAPSED_STORAGE_KEY = "cloud-pricing-column-collapsed";

/** The old per-browser column ids, in column order, and their account keys. */
const OLD_IDS: Record<string, ColumnKey> = {
  provider: "col1",
  collections: "col2",
  service: "col3",
  pricing: "col4",
};

function readObject(key: string): Record<string, unknown> {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

/** The browser's old values as a workspace section, or null when there are none. */
export function readBrowserWorkspace(): WorkspacePreferences | null {
  const widths: Partial<Record<ColumnKey, number>> = {};
  for (const [id, value] of Object.entries(readObject(WIDTHS_STORAGE_KEY))) {
    const key = OLD_IDS[id];
    if (key && typeof value === "number" && Number.isFinite(value) && value > 0) {
      widths[key] = Math.round(value);
    }
  }
  const collapsed: Partial<Record<ColumnKey, boolean>> = {};
  for (const [id, value] of Object.entries(readObject(COLLAPSED_STORAGE_KEY))) {
    const key = OLD_IDS[id];
    if (key && key !== "col4" && typeof value === "boolean") collapsed[key] = value;
  }
  const out: WorkspacePreferences = {};
  if (Object.keys(widths).length > 0) out.column_widths = widths;
  if (Object.keys(collapsed).length > 0) out.collapsed = collapsed;
  return Object.keys(out).length > 0 ? out : null;
}
