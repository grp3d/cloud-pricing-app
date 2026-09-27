/**
 * Per-browser, per-Architecture hand-placed icon positions (016-canvas-icon-layout, FR-006,
 * data-model.md §5). Same `localStorage`-under-try/catch pattern as `diagramLayout.ts`, which
 * persists box positions and sizes: a missing, malformed, or invalid entry is never an error —
 * that icon simply falls back to default placement (`iconLayout.resolvePositions`).
 *
 * Keyed by SKU Selection id, with positions relative to the box's icon area, so moving a
 * service to another box keeps its entry and it is re-validated there.
 */

import type { IconPosition, IconPositions } from "./iconLayout";

function storageKey(architectureId: string): string {
  return `cloud-pricing-icon-layout-${architectureId}`;
}

function isIconPosition(value: unknown): value is IconPosition {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.x === "number" && typeof v.y === "number";
}

export function readIconLayout(architectureId: string): IconPositions {
  try {
    const raw = localStorage.getItem(storageKey(architectureId));
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return {};
    const result: IconPositions = {};
    for (const [id, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (isIconPosition(value)) result[id] = { x: value.x, y: value.y };
    }
    return result;
  } catch {
    return {};
  }
}

function write(architectureId: string, layout: IconPositions): void {
  try {
    localStorage.setItem(storageKey(architectureId), JSON.stringify(layout));
  } catch {
    // Best-effort persistence — see the module comment.
  }
}

export function writeIconPosition(
  architectureId: string,
  selectionId: string,
  position: IconPosition,
): void {
  write(architectureId, { ...readIconLayout(architectureId), [selectionId]: position });
}

/** Saves several positions at once, keeping every other stored entry. */
export function writeIconPositions(architectureId: string, positions: IconPositions): void {
  write(architectureId, { ...readIconLayout(architectureId), ...positions });
}

export function removeIconPosition(architectureId: string, selectionId: string): void {
  const next = readIconLayout(architectureId);
  delete next[selectionId];
  write(architectureId, next);
}
