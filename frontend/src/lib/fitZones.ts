/**
 * Rendered widths for the workspace's three zones (021, research R4). The canvas keeps at
 * least `CANVAS_MIN_WIDTH`; when the window is too narrow for the saved widths, the sidebar
 * gives up width first, then the inspector, each down to its collapsed-rail width. Fitting
 * never changes the saved widths: only a drag does.
 */
import { MIN_WIDTH } from "./columnWidths";

export const CANVAS_MIN_WIDTH = 400;

export interface ZoneSizes {
  sidebar: number;
  sidebarCollapsed: boolean;
  inspector: number;
  inspectorCollapsed: boolean;
}

export interface FittedZones {
  sidebar: number;
  canvas: number;
  inspector: number;
}

export function fitZones(available: number, zones: ZoneSizes): FittedZones {
  let sidebar = zones.sidebarCollapsed ? MIN_WIDTH : Math.max(MIN_WIDTH, zones.sidebar);
  let inspector = zones.inspectorCollapsed ? MIN_WIDTH : Math.max(MIN_WIDTH, zones.inspector);
  let over = sidebar + inspector + CANVAS_MIN_WIDTH - Math.max(0, available);
  if (over > 0) {
    const fromSidebar = Math.min(over, sidebar - MIN_WIDTH);
    sidebar -= fromSidebar;
    over -= fromSidebar;
    const fromInspector = Math.min(over, inspector - MIN_WIDTH);
    inspector -= fromInspector;
  }
  const canvas = Math.max(0, Math.max(0, available) - sidebar - inspector);
  return { sidebar, canvas, inspector };
}
