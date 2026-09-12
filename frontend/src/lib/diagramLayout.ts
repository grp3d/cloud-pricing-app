/**
 * Per-browser, per-Architecture diagram-layout persistence (009-ui-fixes-next-iteration, US7,
 * FR-024, research.md §7a, data-model.md). Modeled directly on `columnWidths.ts`'s existing
 * pattern (`localStorage`-under-try/catch, never throws, silently no-ops when unavailable) and
 * `priorCalculation.ts`'s per-Architecture key scoping — this is genuinely NEW persistence, not
 * a reuse of an existing mechanism: 005/007/008's manual resize was in-session-only, lost on
 * reload (research.md §7a corrects an earlier wrong assumption about this).
 *
 * Stores, per Collection id, the user's manually-set box size and canvas position — the two
 * things a user can adjust that FR-024 requires to survive a reload. Diagram spacing (FR-023)
 * is a static, code-level constant with no per-user adjustment, so there is nothing to persist
 * for it (see spec.md's Assumptions).
 */

export interface CollectionLayoutOverride {
  width: number;
  height: number;
  x: number;
  y: number;
}

export type DiagramLayout = Record<string, CollectionLayoutOverride>;

function storageKey(architectureId: string): string {
  return `cloud-pricing-diagram-layout-${architectureId}`;
}

function isCollectionLayoutOverride(value: unknown): value is CollectionLayoutOverride {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.width === "number" &&
    typeof v.height === "number" &&
    typeof v.x === "number" &&
    typeof v.y === "number"
  );
}

/** Reads the stored layout for one Architecture. A missing key, malformed JSON, or an invalid
 * entry for one Collection never throws — that Collection is simply omitted (falls back to
 * the diagram's own computed layout), matching `columnWidths.ts`'s per-entry tolerance. */
export function readDiagramLayout(architectureId: string): DiagramLayout {
  try {
    const raw = localStorage.getItem(storageKey(architectureId));
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return {};
    const result: DiagramLayout = {};
    for (const [id, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (isCollectionLayoutOverride(value)) result[id] = value;
    }
    return result;
  } catch {
    return {};
  }
}

/** Writes one Collection's layout override, leaving every other stored Collection (in this
 * Architecture) untouched. Silently no-ops if `localStorage` is unavailable — the resize/move
 * just won't survive a reload this session, matching `columnWidths.ts`'s best-effort
 * persistence. */
export function writeCollectionLayout(
  architectureId: string,
  collectionId: string,
  layout: CollectionLayoutOverride,
): void {
  try {
    const next = { ...readDiagramLayout(architectureId), [collectionId]: layout };
    localStorage.setItem(storageKey(architectureId), JSON.stringify(next));
  } catch {
    // See comment above — persistence is best-effort.
  }
}
