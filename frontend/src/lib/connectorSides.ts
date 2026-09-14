/**
 * Per-browser, per-Architecture Connector-side persistence (009-ui-fixes-next-iteration
 * follow-up, new arch spec requirement). Modeled directly on `diagramLayout.ts`'s established
 * pattern (same `cloud-pricing-diagram-` key prefix shape, `localStorage`-under-try/catch,
 * never throws, silently no-ops when unavailable, scoped per Architecture) rather than a
 * backend/DB field — a Connector's attachment side is a per-browser display preference, the
 * same category of thing box size/position/diagram zoom already are, not Architecture data
 * that needs to be shared across browsers or devices.
 *
 * Once a side is assigned to a Connector — whether by `connectorRouting.ts`'s auto-choose
 * algorithm on creation, or a user's own drag-to-reconnect — it's written here and treated as
 * a fixed, sticky choice: `ArchitectureDiagramPanel.tsx` never silently reassigns an already-
 * stored side just because something else on the canvas changed later.
 */

import { isConnectorSide, type ConnectorSide } from "./connectorRouting";

export interface ConnectorSides {
  from: ConnectorSide;
  to: ConnectorSide;
}

export type ConnectorSidesMap = Record<string, ConnectorSides>;

function storageKey(architectureId: string): string {
  return `cloud-pricing-diagram-connector-sides-${architectureId}`;
}

function isConnectorSides(value: unknown): value is ConnectorSides {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return isConnectorSide(v.from) && isConnectorSide(v.to);
}

/** Reads every stored Connector-side assignment for one Architecture. A missing key,
 * malformed JSON, or an invalid entry for one Connector never throws — that Connector is
 * simply omitted (the caller then auto-chooses one, per `connectorRouting.ts`), matching
 * `diagramLayout.ts`'s per-entry tolerance. */
export function readConnectorSides(architectureId: string): ConnectorSidesMap {
  try {
    const raw = localStorage.getItem(storageKey(architectureId));
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return {};
    const result: ConnectorSidesMap = {};
    for (const [id, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (isConnectorSides(value)) result[id] = value;
    }
    return result;
  } catch {
    return {};
  }
}

/** Writes one Connector's side assignment, leaving every other stored Connector (in this
 * Architecture) untouched. Silently no-ops if `localStorage` is unavailable — the assignment
 * just won't survive a reload this session, matching `diagramLayout.ts`'s best-effort
 * persistence. */
export function writeConnectorSides(
  architectureId: string,
  connectorId: string,
  sides: ConnectorSides,
): void {
  try {
    const next = { ...readConnectorSides(architectureId), [connectorId]: sides };
    localStorage.setItem(storageKey(architectureId), JSON.stringify(next));
  } catch {
    // See comment above — persistence is best-effort.
  }
}
