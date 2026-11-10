/**
 * How a connector's arrow style is drawn (019, FR-026, FR-028, research R13). Visual only:
 * `from` → `to`, and so the priced direction, never change (FR-029).
 *
 * - `none`: a plain line.
 * - `one_way`: an arrowhead at the `to` end; reversed, at the `from` end.
 * - `two_way`: an arrowhead at both ends; reversing changes nothing.
 * - `one_to_many` / `many_to_one`: drawn like `one_way` on a connector with two boxes, the
 *   arrowheads pointing at the "many" or the "one" side (branches: US5, phase 9).
 */
import { type EdgeMarker, MarkerType } from "@xyflow/react";

import type { DataConnector } from "../api/client";

export type ArrowStyle = DataConnector["arrow_style"];

export const ARROW_STYLE_LABELS: Record<ArrowStyle, string> = {
  none: "None",
  one_way: "One-way",
  two_way: "Two-way",
  one_to_many: "One-to-many",
  many_to_one: "Many-to-one",
};

/** The styles offered in the picker, in order. */
export const ARROW_STYLES: ArrowStyle[] = ["none", "one_way", "two_way"];

/** Whether Reverse means anything for a style (FR-028). */
export function isDirectional(style: ArrowStyle): boolean {
  return style === "one_way" || style === "one_to_many" || style === "many_to_one";
}

/** 3x React Flow's own default size (010: the default read as too small on this diagram). */
export const ARROW_MARKER: EdgeMarker = { type: MarkerType.ArrowClosed, width: 37.5, height: 37.5 };

/** React Flow edge markers for a connector. The path always runs `from` → `to`, and React
 * Flow points a start marker back along it, so a reversed arrow is a start marker. */
export function connectorMarkers(
  style: ArrowStyle,
  reversed: boolean,
  marker: EdgeMarker = ARROW_MARKER,
): { markerStart?: EdgeMarker; markerEnd?: EdgeMarker } {
  if (style === "none") return {};
  if (style === "two_way") return { markerStart: marker, markerEnd: marker };
  return reversed ? { markerStart: marker } : { markerEnd: marker };
}
