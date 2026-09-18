/**
 * Per-browser, per-Architecture manual Connector-bend persistence. Modeled directly on
 * `connectorSides.ts`'s established pattern (same `cloud-pricing-diagram-` key prefix shape,
 * `localStorage`-under-try/catch, never throws, silently no-ops when unavailable, scoped per
 * Architecture) — a Connector's manually-dragged curve shape is the same category of per-
 * browser display preference box size/position/connector side/diagram zoom already are, not
 * Architecture data that needs to be shared across browsers or devices.
 *
 * Once a Connector has a bend, `ArchitectureDiagramPanel.tsx`'s `OffsetEdge` treats it as
 * taking precedence over auto-routing (the default bezier curve, and the obstacle-avoidance
 * detour) until the user explicitly resets it — the same "sticky until cleared" ethos
 * `connectorSides.ts` already has for attachment sides, just with an actual clear operation
 * here since a bend (unlike a side) has a meaningful "back to automatic" state.
 */

import { type BendControlPoint } from "./connectorRouting";

export interface ConnectorBend {
  /** Ordered control points, in the connector's own chord-relative frame (see
   * `connectorRouting.ts`'s `bendPointToAbsolute`/`absoluteToBendPoint`) — today's UI only ever
   * writes one (a single drag handle produces one bend, rendered as a quadratic curve through
   * it), but the shape is already plural so multi-point bending is additive later, not a
   * migration. */
  controlPoints: BendControlPoint[];
}

export type ConnectorBendsMap = Record<string, ConnectorBend>;

function storageKey(architectureId: string): string {
  return `cloud-pricing-diagram-connector-bends-${architectureId}`;
}

function isBendControlPoint(value: unknown): value is BendControlPoint {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.t === "number" && typeof v.d === "number";
}

function isConnectorBend(value: unknown): value is ConnectorBend {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    Array.isArray(v.controlPoints) &&
    v.controlPoints.length > 0 &&
    v.controlPoints.every(isBendControlPoint)
  );
}

/** Reads every stored Connector bend for one Architecture. A missing key, malformed JSON, or
 * an invalid entry for one Connector never throws — that Connector is simply omitted (the
 * caller then falls back to auto-routing), matching `connectorSides.ts`'s per-entry
 * tolerance. */
export function readConnectorBends(architectureId: string): ConnectorBendsMap {
  try {
    const raw = localStorage.getItem(storageKey(architectureId));
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return {};
    const result: ConnectorBendsMap = {};
    for (const [id, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (isConnectorBend(value)) result[id] = value;
    }
    return result;
  } catch {
    return {};
  }
}

/** Writes one Connector's bend, leaving every other stored Connector (in this Architecture)
 * untouched. Silently no-ops if `localStorage` is unavailable — the bend just won't survive a
 * reload this session, matching `connectorSides.ts`'s best-effort persistence. */
export function writeConnectorBend(
  architectureId: string,
  connectorId: string,
  bend: ConnectorBend,
): void {
  try {
    const next = { ...readConnectorBends(architectureId), [connectorId]: bend };
    localStorage.setItem(storageKey(architectureId), JSON.stringify(next));
  } catch {
    // See comment above — persistence is best-effort.
  }
}

/** Removes one Connector's bend, returning it to auto-routing. Unlike a side (which is always
 * either persisted or freshly auto-chosen, never genuinely "unset"), a bend has a real cleared
 * state — this is how the user gets back to it. */
export function clearConnectorBend(architectureId: string, connectorId: string): void {
  try {
    const next = readConnectorBends(architectureId);
    delete next[connectorId];
    localStorage.setItem(storageKey(architectureId), JSON.stringify(next));
  } catch {
    // See comment above — persistence is best-effort.
  }
}
