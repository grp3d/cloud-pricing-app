/**
 * Per-browser, per-Architecture diagram zoom persistence (009-ui-fixes-next-iteration
 * follow-up). Modeled directly on `diagramLayout.ts`'s established pattern (same
 * `cloud-pricing-diagram-` key prefix shape, `localStorage`-under-try/catch, never throws,
 * silently no-ops when unavailable, scoped per Architecture) — a sibling module rather than a
 * new field on `diagramLayout.ts` itself, since zoom is a property of the *viewport*, not of
 * any one Collection's box. Only the zoom level is persisted here, not pan position — that
 * wasn't asked for, and restoring an old pan offset without also restoring which Collections
 * existed at the time would be more disorienting than useful.
 */

const MIN_STORED_ZOOM = 0.05;
const MAX_STORED_ZOOM = 10;

function storageKey(architectureId: string): string {
  return `cloud-pricing-diagram-zoom-${architectureId}`;
}

/** Reads the stored zoom level for one Architecture, or `null` when nothing valid is stored
 * (missing key, malformed JSON, or an out-of-range number) — the caller falls back to React
 * Flow's own default zoom (1) in that case, matching `diagramLayout.ts`'s per-entry
 * tolerance. */
export function readDiagramZoom(architectureId: string): number | null {
  try {
    const raw = localStorage.getItem(storageKey(architectureId));
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed !== "number" ||
      !Number.isFinite(parsed) ||
      parsed < MIN_STORED_ZOOM ||
      parsed > MAX_STORED_ZOOM
    ) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

/** Writes the current zoom level for one Architecture. Silently no-ops if `localStorage` is
 * unavailable — the zoom just won't survive a reload this session, matching
 * `diagramLayout.ts`'s best-effort persistence. */
export function writeDiagramZoom(architectureId: string, zoom: number): void {
  try {
    localStorage.setItem(storageKey(architectureId), JSON.stringify(zoom));
  } catch {
    // See comment above — persistence is best-effort.
  }
}
