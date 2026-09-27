import "@xyflow/react/dist/style.css";

import {
  BaseEdge,
  Background,
  ConnectionMode,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  NodeResizeControl,
  Panel,
  Position,
  ReactFlow,
  addEdge,
  getBezierPath,
  reconnectEdge,
  useNodes,
  useOnSelectionChange,
  useReactFlow,
  useStore,
  useViewport,
  type Connection,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
  type Viewport,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowUpRight, RefreshCw } from "lucide-react";

import { type Collection, type DataConnector } from "../../api/client";
import { useMeasuredHeight } from "../../hooks/useMeasuredHeight";
import { decideNestingChange } from "../../pages/dropTargetDetection";
import { updateOrderedSelection } from "../../pages/connectorSelection";
import {
  type MeasuredLayoutNode,
  childYOffsets,
  computeMeasuredHeight,
  estimateComponentHeight,
} from "../../pages/nodeLayout";
import { edgeOffsetIndex } from "../../lib/edgeOffset";
import { awsDataTransferLabel } from "../../lib/awsDataTransfer";
import { resolveAwsServiceIcon } from "../../lib/awsServiceIcons";
import {
  findVisibleSlot,
  flowGridPlacer,
  type Rect as PlacementRect,
} from "../../lib/newNodePlacement";
import { decideIconDrop, type DropBox } from "../../lib/iconDrop";
import {
  readIconLayout,
  removeIconPosition,
  writeIconPosition,
  writeIconPositions,
} from "../../lib/iconLayoutStorage";
import {
  ICON,
  MIN_ICON_BOX_WIDTH,
  PAD,
  BORDER,
  contentHeight,
  nearestValidSpot,
  defaultBoxWidth,
  innerWidthOf,
  resolvePositions,
  type IconPosition,
  type IconPositions,
} from "../../lib/iconLayout";
import { buildServicePopupLines, servicePopupAccessibleName } from "../../lib/servicePopup";
import {
  readDiagramLayout,
  writeCollectionLayout,
  type CollectionLayoutOverride,
} from "../../lib/diagramLayout";
import { readDiagramZoom, writeDiagramZoom } from "../../lib/diagramViewport";
import {
  ALL_CONNECTOR_SIDES,
  absoluteToBendPoint,
  buildManualBendRoute,
  chooseConnectorSides,
  isConnectorSide,
  routeAroundObstacles,
  sampleCubicBezier,
  sampleQuadraticBezier,
  type BendControlPoint,
  type ConnectorSide,
  type Point,
  type Rect,
} from "../../lib/connectorRouting";
import { readConnectorSides, writeConnectorSides, type ConnectorSides } from "../../lib/connectorSides";
import {
  clearConnectorBend,
  readConnectorBends,
  writeConnectorBend,
  type ConnectorBend,
} from "../../lib/connectorBends";
import { Button } from "../ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

/** One service on the canvas as its AWS icon (015-canvas-service-icons, FR-001/FR-002/FR-006):
 * the resolved service icon (product-family override, then service code, then the generic
 * fallback — `awsServiceIcons.ts`) in a button that selects the service exactly as the old
 * text row did — 60px since 016-canvas-icon-layout (FR-001, 2.5× the original 24px), absolutely
 * positioned in its box's icon area, and draggable to another spot or into another box. Theme-aware icons (the fallback and AWSDataTransfer's Data Stream icon) render
 * both variants, one hidden per theme. The pixel size is fixed in node space, so it scales with
 * the canvas zoom through React Flow's viewport transform like every other node label (FR-013).
 * Hovering or focusing it shows the service's details one labeled line each (FR-008-FR-011,
 * `servicePopup.ts`), which are also its accessible name (FR-012). The pop-up portals outside
 * the zoomed viewport, so it can't inherit the canvas's scale: its font size tracks the live
 * zoom instead (FR-014, research.md §5) — the tooltip's normal `text-xs` at the canvas's default
 * zoom (the readout's "100%"), proportionally larger or smaller from there. Sized through real
 * `font-size`/`em` rather than a CSS `transform`, so Radix's placement and collision handling
 * still measure the true box. */
function ServiceIconButton({
  selection,
  isSelected,
  onSelectService,
  position,
  onDrop,
}: {
  selection: Collection["sku_selections"][number];
  isSelected: boolean;
  onSelectService: (skuSelectionId: string) => void;
  /** 016-canvas-icon-layout: the icon's top-left within its box's icon area (`iconLayout.ts`). */
  position: IconPosition;
  /** 016-canvas-icon-layout, FR-004–FR-005: called when a drag ends, with the pointer's screen
   * position — the canvas decides where the icon (or service) goes. */
  onDrop?: (selectionId: string, clientX: number, clientY: number) => void;
}) {
  const icon = resolveAwsServiceIcon(selection.service_code, selection.product_family);
  const popupLines = buildServicePopupLines(selection);
  const zoom = useStore((state) => state.transform[2]);
  // Pointer-driven drag (research.md §8). A press that moves no more than DRAG_THRESHOLD screen
  // px is still a click (FR-007); beyond that, a floating copy follows the pointer (rendered
  // over everything, so a box's own overflow never clips it) and the drop is reported up.
  const dragRef = useRef<{ startX: number; startY: number; dragging: boolean } | null>(null);
  const suppressClickRef = useRef(false);
  const [ghost, setGhost] = useState<{ x: number; y: number } | null>(null);
  const ghostSize = ICON * zoom;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={servicePopupAccessibleName(popupLines)}
          aria-pressed={isSelected}
          onPointerDown={(e) => {
            if (!onDrop || e.button !== 0) return;
            e.stopPropagation();
            e.currentTarget.setPointerCapture?.(e.pointerId);
            dragRef.current = { startX: e.clientX, startY: e.clientY, dragging: false };
          }}
          onPointerMove={(e) => {
            const drag = dragRef.current;
            if (!drag) return;
            const moved = Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY);
            if (!drag.dragging && moved <= DRAG_THRESHOLD) return;
            drag.dragging = true;
            setGhost({ x: e.clientX, y: e.clientY });
          }}
          onPointerUp={(e) => {
            const drag = dragRef.current;
            dragRef.current = null;
            e.currentTarget.releasePointerCapture?.(e.pointerId);
            if (!drag?.dragging) return;
            setGhost(null);
            suppressClickRef.current = true;
            onDrop?.(selection.id, e.clientX, e.clientY);
          }}
          onPointerCancel={() => {
            dragRef.current = null;
            setGhost(null);
          }}
          className={`nodrag nopan absolute size-[60px] touch-none rounded-sm p-0 hover:ring-2 hover:ring-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            isSelected ? "ring-2 ring-primary" : ""
          } ${ghost ? "opacity-30" : ""}`}
          style={{ left: position.x, top: position.y }}
          onClick={(e) => {
            e.stopPropagation();
            if (suppressClickRef.current) {
              suppressClickRef.current = false;
              return;
            }
            onSelectService(selection.id);
          }}
        >
          {icon.lightUrl === icon.darkUrl ? (
            <img src={icon.lightUrl} alt="" draggable={false} className="size-[60px]" />
          ) : (
            <>
              <img
                src={icon.lightUrl}
                alt=""
                draggable={false}
                className="size-[60px] dark:hidden"
              />
              <img
                src={icon.darkUrl}
                alt=""
                draggable={false}
                className="hidden size-[60px] dark:block"
              />
            </>
          )}
        </button>
      </TooltipTrigger>
      {ghost &&
        createPortal(
          <img
            src={icon.lightUrl}
            alt=""
            aria-hidden
            className="pointer-events-none fixed z-[1000] rounded-sm opacity-80 shadow-lg"
            style={{
              left: ghost.x - ghostSize / 2,
              top: ghost.y - ghostSize / 2,
              width: ghostSize,
              height: ghostSize,
            }}
          />,
          document.body,
        )}
      <TooltipContent
        className="max-w-[40em] flex-col items-start gap-0 px-[0.8em] py-[0.5em]"
        style={{ fontSize: `calc(var(--text-xs) * ${zoom / DEFAULT_DIAGRAM_ZOOM})` }}
      >
        {popupLines.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </TooltipContent>
    </Tooltip>
  );
}

/** Shared service-list rendering for both node types (004, FR-015). Each listed service is
 * independently clickable (007-ui-overhaul-shadcn, FR-014) — `stopPropagation` keeps that click
 * from also being interpreted as a click on the containing box (which selects the Collection as
 * a whole, unchanged from 002-006). 015-canvas-service-icons (FR-001, FR-005): each service is
 * an icon rather than a `service_code / sku — detail` text row; the same service may repeat.
 * 016-canvas-icon-layout (FR-001–FR-003, FR-008): icons are 60px and absolutely positioned in an
 * icon area — up to 3 per row, 60px apart by default, or wherever they were hand-placed — whose
 * height covers the lowest icon plus room for the region label, so the node's measured height
 * (and a VPC's nested boxes below it) follows. The currently-selected service is marked
 * exclusively (`selectedServiceId` — see `WorkspacePage.tsx`'s `diagramSelection`). */
export function ServiceList({
  skuSelections,
  selectedServiceId,
  onSelectService,
  hideEmptyMessage,
  innerWidth,
  savedPositions,
  onIconDrop,
}: {
  skuSelections: Collection["sku_selections"];
  selectedServiceId?: string;
  onSelectService: (skuSelectionId: string) => void;
  /** 009-ui-fixes-next-iteration follow-up: a VPC with a nested Application Component (which
   * already has its own, visibly-present box, itself possibly *also* reading "No services
   * yet.") passes this — the VPC's own empty-services message is redundant clutter once
   * there's already visible content inside it, not useful information the way it is for a
   * genuinely empty box. `ApplicationComponentNode` (which can never have children) never
   * passes this, so its own "No services yet." is unaffected. */
  hideEmptyMessage?: boolean;
  /** Width of the box's icon area (the box width minus padding and borders). */
  innerWidth: number;
  /** Hand-placed positions by SKU Selection id; anything missing or invalid falls back to the
   * first free default slot (`resolvePositions`). */
  savedPositions?: IconPositions;
  /** 016-canvas-icon-layout, FR-004: reports an icon drag's drop point to the canvas. */
  onIconDrop?: (selectionId: string, clientX: number, clientY: number) => void;
}) {
  const positions = useMemo(
    () =>
      resolvePositions(
        skuSelections.map((s) => s.id),
        savedPositions ?? {},
        innerWidth,
      ),
    [skuSelections, savedPositions, innerWidth],
  );
  if (skuSelections.length === 0) {
    return hideEmptyMessage ? null : (
      <p className="mt-1 text-2xs text-muted-foreground">No services yet.</p>
    );
  }
  return (
    <div className="relative mt-1" style={{ height: contentHeight(positions) }}>
      {skuSelections.map((s) => (
        <ServiceIconButton
          key={s.id}
          selection={s}
          isSelected={s.id === selectedServiceId}
          onSelectService={onSelectService}
          position={positions[s.id]}
          onDrop={onIconDrop}
        />
      ))}
    </div>
  );
}

/** Pointer movement (screen px) below which an icon press is a click, not a drag (FR-007). */
const DRAG_THRESHOLD = 4;
/** Height of a box's name line plus the icon area's top margin — the icon area's offset below
 * the box's inner top edge, used to turn a drop point into an icon-area position. */
const ICON_AREA_TOP = 20;

/** Today's default box widths (002-015) — 016-canvas-icon-layout keeps them as minimums and
 * widens a box only as far as its widest row of icons needs (FR-002, `defaultBoxWidth`). */
const VPC_MIN_WIDTH = 220;
const APPLICATION_MIN_WIDTH = 200;
const NESTED_APPLICATION_MIN_WIDTH = 180;
/** A nested box's left offset inside its VPC (see `position: { x: 20, ... }` below). */
const NESTED_CHILD_INSET = 20;

/** The outer node box's own vertical chrome (unchanged from 005/006 — see nodeLayout.ts). */
const NODE_CHROME_HEIGHT = 2 * 8 + 2 * 2;

/** The diagram panel's own minimum height (FR-004, 008-ui-updates-corrections) — matches the
 * prior `min-h-[600px]` Tailwind class exactly; enforced in `DiagramResizeHandle`'s drag
 * handler now that height is real state rather than a CSS-only constraint. */
const DIAGRAM_MIN_HEIGHT = 600;

/** 009-ui-fixes-next-iteration follow-up: React Flow's native 1:1 zoom (raw `zoom` value 1,
 * what used to display as "100%") renders every box/font too large per live feedback — this
 * is the new "100%" baseline instead. Applied two places below: (1) a brand-new Architecture
 * (or a cleared `localStorage`) now opens already at this raw zoom rather than React Flow's
 * own default of 1, so the *first* thing anyone sees is the smaller sizing, not the old
 * too-big one; (2) the on-canvas readout divides the real (raw) zoom by this before turning
 * it into a percentage, so that raw zoom reads as "100%" instead of "70%". Deliberately a
 * display- and default-only rebase, not a change to any node's actual authored width/height/
 * font classes — `+`/`-`/scroll-to-zoom, `fitView`, and the persisted-zoom round-trip
 * (`diagramViewport.ts`) all keep operating on the same real underlying React Flow zoom value
 * they always did; only what number gets shown for it, and where a fresh view starts, moves. */
const DEFAULT_DIAGRAM_ZOOM = 0.7;

const CONNECTOR_SIDE_POSITION: Record<ConnectorSide, Position> = {
  top: Position.Top,
  right: Position.Right,
  bottom: Position.Bottom,
  left: Position.Left,
};

/** Four connection points per box — one per side — replacing the prior fixed single
 * `Position.Left` target / `Position.Right` source pair (009-ui-fixes-next-iteration
 * follow-up, new arch spec requirement: auto-routed Connectors need a side to route *to*, and
 * dragging an existing Connector's endpoint to a different side needs somewhere to drop it).
 * Shared by both node types so they stay identical.
 *
 * Each side renders both a `source` and a `target` Handle sharing the same `id` — React
 * Flow's own supported pattern for "this one visual connection point can be either end of an
 * edge," needed because a Connector's `from`/`to` is a labeled pair of Collections, not an
 * inherently directional arrow a user should have to think about in terms of source vs.
 * target. `connectionMode="loose"` (set on `<ReactFlow>` below) is what actually allows
 * dragging *from* a target handle or *onto* a source handle — this pairing alone doesn't. */
function SideHandles() {
  return (
    <>
      {ALL_CONNECTOR_SIDES.map((side) => (
        <Fragment key={side}>
          <Handle type="source" position={CONNECTOR_SIDE_POSITION[side]} id={side} />
          <Handle type="target" position={CONNECTOR_SIDE_POSITION[side]} id={side} />
        </Fragment>
      ))}
    </>
  );
}

/** Absolute canvas position (not React Flow's own parent-relative `position` for a nested
 * child) plus size for one node, resolved by walking up its `parentId` chain — needed because
 * `connectorRouting.ts`'s geometry is only meaningful in one shared coordinate space, and a
 * Collection nested inside a VPC has a `position` relative to that VPC, not the canvas. */
function absoluteRect(nodeId: string, nodesById: Map<string, Node>): Rect | null {
  const node = nodesById.get(nodeId);
  if (!node) return null;
  let x = node.position.x;
  let y = node.position.y;
  let parentId = node.parentId;
  while (parentId) {
    const parent = nodesById.get(parentId);
    if (!parent) break;
    x += parent.position.x;
    y += parent.position.y;
    parentId = parent.parentId;
  }
  const width = typeof node.style?.width === "number" ? node.style.width : 0;
  const height = typeof node.style?.height === "number" ? node.style.height : 0;
  return { x, y, width, height };
}

/** A node's own id plus every ancestor's (walking `parentId`) — used to exclude a Connector's
 * own endpoint boxes, and *their* containing VPC(s), from its obstacle-avoidance check
 * (`routeAroundObstacles` below). A nested Application's own handle sits on its own boundary,
 * inside its parent VPC's boundary by construction — treating that parent as an "obstacle"
 * would misfire on every single Connector attached to a nested box, not just ones that
 * actually cross some unrelated box. */
function selfAndAncestorIds(nodeId: string, nodesById: Map<string, Node>): Set<string> {
  const ids = new Set<string>();
  let id: string | undefined = nodeId;
  while (id) {
    ids.add(id);
    id = nodesById.get(id)?.parentId;
  }
  return ids;
}

/** Extracts the 4 control points (`M x,y C cx1,cy1 cx2,cy2 x,y`) React Flow's `getBezierPath`
 * always emits, so `OffsetEdge` below can sample the *actual* curve it's about to render for
 * `routeAroundObstacles`'s obstacle check (see that function's own doc comment) rather than
 * re-deriving React Flow's internal curvature formula independently — parsing its own output
 * stays correct even if that internal formula ever changes. `null` only if the format itself
 * ever changes (defensive; every real `getBezierPath` call has matched this since the library's
 * initial release). */
function parseCubicBezier(path: string): [Point, Point, Point, Point] | null {
  const match = /M([-\d.]+),([-\d.]+)C([-\d.]+),([-\d.]+) ([-\d.]+),([-\d.]+) ([-\d.]+),([-\d.]+)/.exec(
    path,
  );
  if (!match) return null;
  const n = match.slice(1).map(Number);
  return [
    { x: n[0], y: n[1] },
    { x: n[2], y: n[3] },
    { x: n[4], y: n[5] },
    { x: n[6], y: n[7] },
  ];
}

const EMPTY_SIDE_USAGE: Record<ConnectorSide, number> = { top: 0, right: 0, bottom: 0, left: 0 };

/** Resolves every Connector's attachment sides — the persisted one (`connectorSides.ts`) if
 * it has one, otherwise a freshly `chooseConnectorSides`-computed one (009-ui-fixes-next-
 * iteration follow-up, new arch spec requirement) — in one pass, so two Connectors newly
 * created in the same batch don't both independently "see" the same open side and collide.
 * Shared by `initialEdges` (needs the resolved value immediately, for this render's paint)
 * and the persistence `useEffect` below (needs to know exactly which ones are new, to write
 * only those) — both call this same function rather than duplicating the logic, so they can
 * never disagree with each other about what a given Connector's sides *should* be. Silently
 * skips (omits from the result) a Connector whose endpoint Collection isn't found among
 * `nodes` — should never happen, but "no line drawn" beats crashing the whole diagram over
 * one bad reference.
 *
 * Live user rule change: only tracks each Collection's *arrival*-side usage (`sides.to`) now
 * — `chooseConnectorSides`' `fromSide` no longer considers occupancy at all (multiple
 * Connectors may depart the same side), so there's nothing for a `from` assignment to bump. */
function resolveConnectorSides(
  connectors: DataConnector[],
  nodes: Node[],
  persisted: Record<string, ConnectorSides>,
): { resolved: Map<string, ConnectorSides>; newlyComputed: Map<string, ConnectorSides> } {
  const nodesById = new Map(nodes.map((n) => [n.id, n]));
  const toUsageByCollection = new Map<string, Record<ConnectorSide, number>>();
  const bumpToUsage = (collectionId: string, side: ConnectorSide) => {
    const usage = { ...(toUsageByCollection.get(collectionId) ?? EMPTY_SIDE_USAGE) };
    usage[side] += 1;
    toUsageByCollection.set(collectionId, usage);
  };

  const resolved = new Map<string, ConnectorSides>();
  const newlyComputed = new Map<string, ConnectorSides>();

  // First pass: every already-persisted Connector claims its "to" side's usage slot up front,
  // so a same-pass newly-computed Connector correctly sees it as occupied regardless of which
  // order `connectors` happens to list the two groups in.
  for (const conn of connectors) {
    const sides = persisted[conn.id];
    if (!sides) continue;
    resolved.set(conn.id, sides);
    bumpToUsage(conn.to_collection_id, sides.to);
  }

  for (const conn of connectors) {
    if (resolved.has(conn.id)) continue;
    const fromRect = absoluteRect(conn.from_collection_id, nodesById);
    const toRect = absoluteRect(conn.to_collection_id, nodesById);
    if (!fromRect || !toRect) continue;
    const { fromSide, toSide } = chooseConnectorSides(
      fromRect,
      toRect,
      toUsageByCollection.get(conn.to_collection_id) ?? EMPTY_SIDE_USAGE,
    );
    const sides: ConnectorSides = { from: fromSide, to: toSide };
    resolved.set(conn.id, sides);
    newlyComputed.set(conn.id, sides);
    bumpToUsage(conn.to_collection_id, toSide);
  }

  return { resolved, newlyComputed };
}

/** 009-ui-fixes-next-iteration, US7, FR-020/021: a single resize control at the bottom-right
 * corner only (dropping `<NodeResizer>`'s default all-eight-handle set), with a visible
 * corner-grip affordance styled consistently across both node types. Shared so both components
 * render it identically. */
function BottomRightResizeControl({
  minWidth,
  minHeight,
  onResizeEnd,
}: {
  minWidth: number;
  minHeight: number;
  onResizeEnd: (width: number, height: number, x: number, y: number) => void;
}) {
  return (
    <NodeResizeControl
      position="bottom-right"
      minWidth={minWidth}
      minHeight={minHeight}
      onResizeEnd={(_, params) => onResizeEnd(params.width, params.height, params.x, params.y)}
      style={{ background: "transparent", border: "none" }}
    >
      <div
        aria-hidden
        className="absolute right-0 bottom-0 size-2.5 translate-x-1/2 translate-y-1/2 cursor-se-resize rounded-[2px] border border-primary bg-background"
      />
    </NodeResizeControl>
  );
}

interface ApplicationComponentNodeData {
  [key: string]: unknown;
  label: string;
  skuSelections: Collection["sku_selections"];
  minHeight: number;
  isSelected: boolean;
  selectedServiceId?: string;
  onMeasuredHeight: (height: number) => void;
  onSelectService: (skuSelectionId: string) => void;
  onManualResize: (width: number, height: number, x: number, y: number) => void;
  /** 010-multi-region-support, spec FR-019: shown in the bottom-right corner only while
   * `isNested` is false — once nested inside a VPC, the VPC's own label already conveys it. */
  region: string;
  isNested: boolean;
  /** 016-canvas-icon-layout: the box's width, which the icon area's width derives from. */
  boxWidth: number;
  /** 016-canvas-icon-layout, FR-006: this Architecture's hand-placed icon positions. */
  savedPositions: IconPositions;
  onIconDrop: (selectionId: string, clientX: number, clientY: number) => void;
}

/** Custom node type for an Application Component (spec FR-007, 005, 006). See prior features'
 * research.md for why height is measured, not estimated, and why Handles are rendered
 * explicitly. 007 adds per-service click targets via `ServiceList`'s `onSelectService`. 008
 * adds `onManualResize` (FR-001, research.md §1a) — reports a user's drag-to-resize back up to
 * `ArchitectureDiagramPanel` so the next `initialNodes` recompute (triggered by *any* box's
 * content changing, not just this one) preserves it instead of silently reverting it.
 *
 * `<NodeResizer>` is now a sibling of the scrollable content box, not a child of it (008,
 * FR-001) — found live: with `overflow-auto` on the *same* element that contained
 * `NodeResizer`, its drag handles (which render centered on/just outside the node's own
 * border for easier grabbing) were being clipped by that same `overflow-auto`, so they were
 * never actually visible or clickable regardless of selection state — a more fundamental
 * blocker than the `initialNodes`-resync clobbering bug above, and the real reason manual
 * resize "didn't work" at all, confirmed by zooming into a selected node's corners live and
 * finding no handle rendered there for *any* node, nested or top-level. */
function ApplicationComponentNode({ data, selected }: NodeProps) {
  const {
    label,
    skuSelections,
    minHeight,
    isSelected,
    selectedServiceId,
    onMeasuredHeight,
    onSelectService,
    onManualResize,
    region,
    isNested,
    boxWidth,
    savedPositions,
    onIconDrop,
  } = data as unknown as ApplicationComponentNodeData;
  const [contentRef, measuredHeight] = useMeasuredHeight<HTMLDivElement>();

  useEffect(() => {
    if (measuredHeight !== null) onMeasuredHeight(measuredHeight + NODE_CHROME_HEIGHT);
  }, [measuredHeight, onMeasuredHeight]);

  return (
    <div className="relative h-full w-full">
      {selected && (
        <BottomRightResizeControl minWidth={160} minHeight={minHeight} onResizeEnd={onManualResize} />
      )}
      <SideHandles />
      <div
        // 009-ui-fixes-next-iteration, US7, FR-018: darker border shade than 008's
        // `border-border` (verified live against both light and dark theme).
        className={`box-border h-full w-full overflow-auto rounded bg-card p-2 ${
          selected ? "border-2 border-primary" : "border border-gray-400 dark:border-gray-600"
        }`}
      >
        <div ref={contentRef} className="h-auto">
          <strong className={`text-2xs ${isSelected ? "underline" : ""}`}>{label}</strong>
          <ServiceList
            skuSelections={skuSelections}
            selectedServiceId={selectedServiceId}
            onSelectService={onSelectService}
            innerWidth={innerWidthOf(boxWidth)}
            savedPositions={savedPositions}
            onIconDrop={onIconDrop}
          />
        </div>
      </div>
      {/* 010-multi-region-support, spec FR-019: only while unnested — a nested Application's
          containing VPC already shows its region. */}
      {!isNested && (
        <span className="absolute bottom-1 right-1 text-2xs text-muted-foreground">{region}</span>
      )}
    </div>
  );
}

interface VpcNodeData {
  [key: string]: unknown;
  label: string;
  skuSelections: Collection["sku_selections"];
  minHeight: number;
  isSelected: boolean;
  selectedServiceId?: string;
  onMeasuredHeight: (height: number) => void;
  onSelectService: (skuSelectionId: string) => void;
  onManualResize: (width: number, height: number, x: number, y: number) => void;
  /** 009-ui-fixes-next-iteration follow-up: whether this VPC has at least one nested
   * Application Component — see `ServiceList`'s `hideEmptyMessage` for why this suppresses
   * the VPC's own "No services yet." text rather than being shown unconditionally. */
  hasChildren: boolean;
  /** 010-multi-region-support, spec FR-018: shown in the bottom-right corner, always. */
  region: string;
  /** 016-canvas-icon-layout: the box's width, which the icon area's width derives from. */
  boxWidth: number;
  /** 016-canvas-icon-layout, FR-006: this Architecture's hand-placed icon positions. */
  savedPositions: IconPositions;
  onIconDrop: (selectionId: string, clientX: number, clientY: number) => void;
}

/** Custom node type for a VPC (002-006). 007 adds the same per-service click targets; 008
 * adds `onManualResize` and moves `<NodeResizer>` out of the scrollable content box — see
 * `ApplicationComponentNode`'s comment above for both (FR-001). */
function VpcNode({ data, selected }: NodeProps) {
  const {
    label,
    skuSelections,
    minHeight,
    isSelected,
    selectedServiceId,
    onMeasuredHeight,
    onSelectService,
    onManualResize,
    hasChildren,
    region,
    boxWidth,
    savedPositions,
    onIconDrop,
  } = data as unknown as VpcNodeData;
  const [contentRef, measuredHeight] = useMeasuredHeight<HTMLDivElement>();

  useEffect(() => {
    if (measuredHeight !== null) onMeasuredHeight(measuredHeight + NODE_CHROME_HEIGHT);
  }, [measuredHeight, onMeasuredHeight]);

  return (
    <div className="relative h-full w-full">
      {selected && (
        <BottomRightResizeControl minWidth={220} minHeight={minHeight} onResizeEnd={onManualResize} />
      )}
      <SideHandles />
      <div
        // 009-ui-fixes-next-iteration, US7, FR-018: darker resting border than 008's
        // `border-primary` alone (which didn't otherwise distinguish selected from
        // unselected); selection still highlights via `border-primary`.
        className={`box-border h-full w-full overflow-auto rounded p-2 ${
          selected ? "border-2 border-primary" : "border-2 border-gray-600 dark:border-gray-400"
        }`}
      >
        <div ref={contentRef} className="h-auto">
          <strong className={`text-2xs ${isSelected ? "underline" : ""}`}>{label}</strong>
          <ServiceList
            skuSelections={skuSelections}
            selectedServiceId={selectedServiceId}
            onSelectService={onSelectService}
            hideEmptyMessage={hasChildren}
            innerWidth={innerWidthOf(boxWidth)}
            savedPositions={savedPositions}
            onIconDrop={onIconDrop}
          />
        </div>
      </div>
      {/* 010-multi-region-support, spec FR-018: always shown for a VPC. */}
      <span className="absolute bottom-1 right-1 text-2xs text-muted-foreground">{region}</span>
    </div>
  );
}

const nodeTypes = {
  applicationComponent: ApplicationComponentNode,
  vpc: VpcNode,
};

/** Drag handle for manually reshaping a Connector's curve (live user request, effort/design
 * discussion landed on a chord-relative control point — see `connectorRouting.ts`'s
 * `bendPointToAbsolute`/`absoluteToBendPoint`/`buildManualBendRoute`). Rendered via
 * `EdgeLabelRenderer` (React Flow's HTML-overlay portal for edges, positioned in flow space via
 * a `translate()` transform, per its own documented usage pattern) rather than as SVG, so it
 * can use the same `onPointerDown`/`setPointerCapture`/`pointermove` pattern already proven
 * elsewhere in this codebase (`PopoutCanvasDialog.tsx`'s drag/resize handles) instead of React
 * Flow's own node-dragging machinery, which only applies to nodes.
 *
 * `point` is always wherever the rendered curve currently actually passes (`OffsetEdge`'s
 * `activeBendPoint`converted to an absolute position, or that same edge's own already-computed
 * label position when no bend exists yet), so the handle never drifts from what it visually
 * controls and is always grabbable exactly on the line. `onDrag` fires on every pointer move
 * with the live position already converted to flow space (`screenToFlowPosition`) — `OffsetEdge`
 * re-derives the chord-relative bend from it each time, so the curve tracks the cursor during
 * the drag itself, not just after release. `onDragEnd` commits (persists) the last live
 * position; double-click resets the Connector to automatic routing. `nodrag nopan` plus
 * `pointerEvents: "all"` are required for an interactive `EdgeLabelRenderer` child per its own
 * doc comment — without them React Flow's pane-pan gesture and node-drag-suppression classes
 * swallow the pointer events before this handle ever sees them. */
function EdgeBendHandle({
  point,
  onDrag,
  onDragEnd,
  onReset,
}: {
  point: Point;
  onDrag: (flowPoint: Point) => void;
  onDragEnd: () => void;
  onReset: () => void;
}) {
  const { screenToFlowPosition } = useReactFlow();

  return (
    <EdgeLabelRenderer>
      <div
        role="button"
        aria-label="Drag to bend this connector's curve; double-click to reset it to automatic routing"
        title="Drag to bend · double-click to reset"
        className="nodrag nopan absolute size-2.5 cursor-grab rounded-full border border-primary bg-background shadow active:cursor-grabbing"
        style={{
          pointerEvents: "all",
          // Found live: `.react-flow__edgelabel-renderer` has no `z-index` of its own (so its
          // children stack at the same level as it does, by plain DOM order) while every
          // `.react-flow__node` carries an explicit inline `z-index` (0 normally, elevated
          // further on selection/drag) — for a short Connector whose curve midpoint lands
          // near/under one of its own endpoint boxes, that box's own content was winning the
          // hit-test and completely swallowing clicks on this handle. A comfortably high
          // explicit `zIndex` here establishes its own stacking context that wins regardless.
          zIndex: 1000,
          transform: `translate(-50%, -50%) translate(${point.x}px, ${point.y}px)`,
        }}
        onDoubleClick={(e) => {
          e.stopPropagation();
          onReset();
        }}
        onPointerDown={(e) => {
          e.stopPropagation();
          const target = e.currentTarget;
          target.setPointerCapture(e.pointerId);

          const handleMove = (moveEvent: PointerEvent) => {
            onDrag(screenToFlowPosition({ x: moveEvent.clientX, y: moveEvent.clientY }));
          };
          const handleUp = () => {
            target.removeEventListener("pointermove", handleMove);
            target.removeEventListener("pointerup", handleUp);
            onDragEnd();
          };
          target.addEventListener("pointermove", handleMove);
          target.addEventListener("pointerup", handleUp);
        }}
      />
    </EdgeLabelRenderer>
  );
}

/** Custom edge renderer for parallel Connectors (009-ui-fixes-next-iteration, US4, FR-010,
 * research.md §4). The first edge in a source/target pair group (`offsetIndex` 0) renders as
 * React Flow's normal bezier path, unchanged. Every subsequent one is displaced perpendicular
 * to the straight line between the two endpoints — this works regardless of node orientation
 * (horizontal, vertical, diagonal), unlike `pathOptions.curvature` (tried first, rejected: for
 * `Position.Left`/`Position.Right` handles on horizontally-aligned nodes — this diagram's most
 * common layout — curvature only extends the control points horizontally, producing an
 * identical-looking path for every offset; confirmed live by inspecting the rendered SVG `d`
 * attributes, which were byte-for-byte identical across differently-curved edges).
 *
 * Live user report: neither of those paths knows about any *other* box on the canvas, so a
 * Connector could render straight through one sitting between its own two endpoints.
 * `routeAroundObstacles` detects that and returns a short detour route around it instead;
 * `defaultPath`/`defaultSamples` below (computed first) are always this edge's *own*
 * unobstructed bezier/perpendicular-offset curve, used two ways: as the final rendered path
 * when nothing blocks it, and — live user report #2 — as what actually gets obstacle-tested,
 * not just the straight `source`→`target` line. That straight-line-only check first shipped
 * with this feature missed a VPC sitting squarely under a bulging default bezier curve whose
 * *straight* source/target line happened to clear it; sampling the real curve (`sampleCubic-
 * Bezier`/`sampleQuadraticBezier`) catches that. Obstacles are recomputed here, live, from
 * `useNodes()` (React Flow's own current-node-positions hook) rather than precomputed once in
 * `initialEdges` below — found live: `initialEdges` deliberately only recomputes when
 * `connectors` itself changes (its own comment explains why), so obstacle rects sourced from
 * there would go stale the moment a box is dragged *after* a Connector already exists, exactly
 * the case this feature needs to keep handling.
 *
 * A detour route is drawn as a single cubic Bezier through its 4 points as *control* points
 * (`M source C corner1 corner2 target`), not the sharp right-angle polyline this first shipped
 * with — live user request, matching a reference screenshot of a smooth curve swooping around
 * an obstacle. `routeAroundObstacles`'s own doc comment covers why this still stays clear of
 * the obstacle in the common case this feature targets.
 *
 * A manual bend (`activeBendPoint` below, live user request) takes precedence over both of the
 * above when present — checked first, before `routed`/`defaultPath` are even considered for
 * rendering (though both are still *computed* regardless, since hooks can't be called
 * conditionally; harmless, just unused work on a bent Connector). `bend`/`dragPreview` are
 * local component state, not derived from `liveNodes` like the obstacle detour is — a manual
 * bend's *shape* doesn't need to react to other boxes moving the way auto-routing does, only
 * to its own two endpoints (via `bendPointToAbsolute`'s live `source`/`target` recompute) —
 * but it does mean a bend made in one `ArchitectureDiagramPanel` instance (e.g. the pop-out)
 * isn't reflected in another simultaneously-open instance of the same canvas until that
 * instance's `OffsetEdge` remounts, the same category of limitation `connectorSides.ts`
 * assignments already have outside the `connectors`-list-change sync path. */
function OffsetEdge({
  id,
  source,
  target,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  style,
  label,
  labelStyle,
  data,
}: EdgeProps) {
  const offsetIndex = (data?.offsetIndex as number | undefined) ?? 0;
  const architectureId = data?.architectureId as string | undefined;
  // Not React Flow's own `selected` prop — see the doc comment on `data.isSelected` where
  // `initialEdges` sets it, below.
  const isSelected = Boolean(data?.isSelected);
  const liveNodes = useNodes();

  const [bend, setBend] = useState<ConnectorBend | null>(() =>
    architectureId ? (readConnectorBends(architectureId)[id] ?? null) : null,
  );
  // Live position while a drag is in progress; `null` the rest of the time. Kept separate from
  // `bend` (the last *persisted* value) so a drag that ends up getting cancelled some other way
  // (e.g. the Connector gets deleted mid-drag) never leaves stale in-progress state mistaken
  // for a committed one.
  const [dragPreview, setDragPreview] = useState<BendControlPoint | null>(null);

  const handleBendDrag = useCallback(
    (flowPoint: Point) => {
      setDragPreview(
        absoluteToBendPoint({ x: sourceX, y: sourceY }, { x: targetX, y: targetY }, flowPoint),
      );
    },
    [sourceX, sourceY, targetX, targetY],
  );

  const handleBendDragEnd = useCallback(() => {
    setDragPreview((current) => {
      if (current && architectureId) {
        const next: ConnectorBend = { controlPoints: [current] };
        setBend(next);
        writeConnectorBend(architectureId, id, next);
      }
      return null;
    });
  }, [architectureId, id]);

  const handleBendReset = useCallback(() => {
    setBend(null);
    setDragPreview(null);
    if (architectureId) clearConnectorBend(architectureId, id);
  }, [architectureId, id]);

  const activeBendPoint = dragPreview ?? bend?.controlPoints[0] ?? null;

  const { defaultPath, defaultLabelX, defaultLabelY, defaultSamples } = useMemo(() => {
    if (offsetIndex === 0) {
      const [path, labelX, labelY] = getBezierPath({
        sourceX,
        sourceY,
        sourcePosition,
        targetX,
        targetY,
        targetPosition,
      });
      const controlPoints = parseCubicBezier(path);
      const samples = controlPoints
        ? sampleCubicBezier(controlPoints[0], controlPoints[1], controlPoints[2], controlPoints[3], 16)
        : [{ x: sourceX, y: sourceY }, { x: targetX, y: targetY }];
      return { defaultPath: path, defaultLabelX: labelX, defaultLabelY: labelY, defaultSamples: samples };
    }

    const dx = targetX - sourceX;
    const dy = targetY - sourceY;
    const length = Math.hypot(dx, dy) || 1;
    // Unit normal to the source->target line, so the offset is perpendicular regardless of the
    // line's own angle.
    const nx = -dy / length;
    const ny = dx / length;
    const direction = offsetIndex % 2 === 1 ? 1 : -1;
    const magnitude = 24 * Math.ceil(offsetIndex / 2) * direction;
    const midX = (sourceX + targetX) / 2 + nx * magnitude;
    const midY = (sourceY + targetY) / 2 + ny * magnitude;
    const path = `M${sourceX},${sourceY} Q${midX},${midY} ${targetX},${targetY}`;
    const samples = sampleQuadraticBezier(
      { x: sourceX, y: sourceY },
      { x: midX, y: midY },
      { x: targetX, y: targetY },
      16,
    );
    return { defaultPath: path, defaultLabelX: midX, defaultLabelY: midY, defaultSamples: samples };
  }, [offsetIndex, sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition]);

  const routed = useMemo(() => {
    const nodesById = new Map(liveNodes.map((n) => [n.id, n]));
    const excluded = new Set([
      ...selfAndAncestorIds(source, nodesById),
      ...selfAndAncestorIds(target, nodesById),
    ]);
    const obstacles = liveNodes
      .filter((n) => !excluded.has(n.id))
      .map((n) => absoluteRect(n.id, nodesById))
      .filter((r): r is Rect => r !== null);
    return routeAroundObstacles(
      { x: sourceX, y: sourceY },
      { x: targetX, y: targetY },
      obstacles,
      // Same magnitude scale as the perpendicular offset above, unsigned here since
      // `routeAroundObstacles` already pushes further from the obstacle regardless of which
      // side it detours around — disambiguates multiple parallel Connectors that all need to
      // detour around the same box, the same way the offset curve already disambiguates
      // multiple parallel *unobstructed* ones.
      offsetIndex > 0 ? 24 * Math.ceil(offsetIndex / 2) : 0,
      defaultSamples,
      // Live user report #3: without these, the detour's final approach had no relation to the
      // target's actual attached side, so the arrowhead (oriented to the path's own tangent at
      // its endpoint) could point in an unrelated direction instead of into the box — see
      // `routeAroundObstacles`'s own doc comment. `sourcePosition`/`targetPosition` are
      // `@xyflow/react`'s `Position` enum, whose values ("top"/"right"/"bottom"/"left") are the
      // exact same strings as `ConnectorSide`; `isConnectorSide` narrows the type safely rather
      // than casting.
      isConnectorSide(sourcePosition) ? sourcePosition : undefined,
      isConnectorSide(targetPosition) ? targetPosition : undefined,
    );
  }, [
    liveNodes,
    source,
    target,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    offsetIndex,
    defaultSamples,
  ]);

  if (activeBendPoint) {
    const src = { x: sourceX, y: sourceY };
    const tgt = { x: targetX, y: targetY };
    const { sourceStub, control, targetStub, through } = buildManualBendRoute(
      src,
      tgt,
      activeBendPoint,
      isConnectorSide(sourcePosition) ? sourcePosition : undefined,
      isConnectorSide(targetPosition) ? targetPosition : undefined,
    );
    // Same stub-bracketed shape as the obstacle detour below (`L` stubs around a `Q` curve, not
    // a `C` — a manual bend only ever has the one solved control point) — for the same reason:
    // the arrowhead must still point straight into the target box regardless of how the curve
    // in between is bent.
    const path = `M${src.x},${src.y} L${sourceStub.x},${sourceStub.y} Q${control.x},${control.y} ${targetStub.x},${targetStub.y} L${tgt.x},${tgt.y}`;
    return (
      <>
        <BaseEdge
          id={id}
          path={path}
          markerEnd={markerEnd}
          style={style}
          label={label}
          labelStyle={labelStyle}
          labelX={through.x}
          labelY={through.y}
        />
        {isSelected && (
          <EdgeBendHandle
            point={through}
            onDrag={handleBendDrag}
            onDragEnd={handleBendDragEnd}
            onReset={handleBendReset}
          />
        )}
      </>
    );
  }

  if (routed) {
    const [p0, p1, p2, p3, p4, p5] = routed;
    // Straight stub segments (`p0`→`p1`, `p4`→`p5`) leave/enter perpendicular to each box's
    // actual attached side — this is what keeps the arrowhead pointing into the box, since its
    // marker orients to the path's own tangent at that final vertex. The curved middle
    // (`p1`→`p2`→`p3`→`p4`, drawn as a single cubic Bezier using `p2`/`p3` as control points)
    // is what actually swoops around the obstacle.
    const path = `M${p0.x},${p0.y} L${p1.x},${p1.y} C${p2.x},${p2.y} ${p3.x},${p3.y} ${p4.x},${p4.y} L${p5.x},${p5.y}`;
    // The midpoint of the detour's own curved middle segment (the part that's actually clearing
    // the obstacle) reads better than the path's literal midpoint, which can land on one of the
    // short stub segments right next to a box. Also where a fresh manual bend starts from if the
    // user grabs the handle here — see `EdgeBendHandle`'s own doc comment.
    const labelX = (p1.x + p4.x) / 2;
    const labelY = (p1.y + p4.y) / 2;
    return (
      <>
        <BaseEdge
          id={id}
          path={path}
          markerEnd={markerEnd}
          style={style}
          label={label}
          labelStyle={labelStyle}
          labelX={labelX}
          labelY={labelY}
        />
        {isSelected && (
          <EdgeBendHandle
            point={{ x: labelX, y: labelY }}
            onDrag={handleBendDrag}
            onDragEnd={handleBendDragEnd}
            onReset={handleBendReset}
          />
        )}
      </>
    );
  }

  return (
    <>
      <BaseEdge
        id={id}
        path={defaultPath}
        markerEnd={markerEnd}
        style={style}
        label={label}
        labelStyle={labelStyle}
        labelX={defaultLabelX}
        labelY={defaultLabelY}
      />
      {isSelected && (
        <EdgeBendHandle
          point={{ x: defaultLabelX, y: defaultLabelY }}
          onDrag={handleBendDrag}
          onDragEnd={handleBendDragEnd}
          onReset={handleBendReset}
        />
      )}
    </>
  );
}

const edgeTypes = {
  offset: OffsetEdge,
};

/**
 * The diagram panel's own bottom-right resize grip (009-ui-fixes-next-iteration follow-up,
 * replacing the outer `<div>`'s native CSS `resize-y`). Found live (user report): dragging
 * that corner moved the architecture's Collections around instead of resizing the panel.
 * Root cause was two-fold — (1) the native resize grip's real hit-region turned out to be a
 * precise ~15px inset from the true corner (confirmed live via `elementFromPoint` sampling
 * pixel-by-pixel out from the corner), easy to miss by a pixel or two and fall through onto
 * `.react-flow__pane` underneath, which happily treats *any* stray drag as a canvas pan; and
 * (2) even a successful native resize was never actually kept — the outer `<div>` was passed
 * a hardcoded `style={{ height: 640 }}` rather than a React-state-backed value, so the *next*
 * unrelated re-render (selecting anything, adding a Service, anything) silently snapped the
 * browser's own DOM mutation back to 640 regardless of what the user had just dragged it to.
 * `ColumnResizeHandle` (`WorkspacePage.tsx`) already solved the equivalent problem for the
 * horizontal column-width dividers with a plain `onPointerDown`/`setPointerCapture` handler
 * instead of relying on any native/implicit browser mechanism — this is that same proven
 * pattern, vertical instead of horizontal, sized generously (16px) so it isn't as easy to
 * miss as the browser's own native grip was.
 */
function DiagramResizeHandle({ onDrag }: { onDrag: (deltaY: number) => void }) {
  const lastYRef = useRef(0);

  return (
    <div
      role="separator"
      aria-orientation="horizontal"
      aria-label="Resize architecture diagram height"
      className="absolute right-0 bottom-0 z-10 size-4 cursor-ns-resize touch-none rounded-br border-border/0 bg-transparent hover:bg-primary/20 active:bg-primary/30"
      onPointerDown={(e) => {
        e.preventDefault();
        lastYRef.current = e.clientY;
        const target = e.currentTarget;
        target.setPointerCapture(e.pointerId);

        const handleMove = (moveEvent: PointerEvent) => {
          const deltaY = moveEvent.clientY - lastYRef.current;
          lastYRef.current = moveEvent.clientY;
          onDrag(deltaY);
        };
        const handleUp = () => {
          target.removeEventListener("pointermove", handleMove);
          target.removeEventListener("pointerup", handleUp);
        };
        target.addEventListener("pointermove", handleMove);
        target.addEventListener("pointerup", handleUp);
      }}
    >
      {/* Same three-diagonal-line grip glyph the native browser resize handle it replaces
          already used — familiar, no relearning, just a bigger and more reliable target. */}
      <svg viewBox="0 0 16 16" className="size-full text-muted-foreground" aria-hidden="true">
        <path
          d="M14 3 L3 14 M14 8 L8 14 M14 13 L13 14"
          stroke="currentColor"
          strokeWidth="1.25"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

export interface ArchitectureDiagramPanelProps {
  /** 009-ui-fixes-next-iteration, US7, FR-024: scopes the new diagram-layout persistence to
   * this Architecture (`lib/diagramLayout.ts`). */
  architectureId: string;
  collections: Collection[];
  connectors: DataConnector[];
  ownHeights: Record<string, number>;
  reportHeight: (id: string, height: number) => void;
  /** 009-ui-fixes-next-iteration, US7, FR-025: precisely which one diagram object is
   * currently selected (for underlining its name) — see `WorkspacePage.tsx`'s
   * `diagramSelection`, which is NOT simply "whichever Collection/Connector id is set" since
   * selecting a Service also sets its containing Collection's id for column-3 purposes. */
  diagramSelection: { kind: "collection" | "connector" | "service"; id: string } | null;
  onSelectedNodeIdsChange: (ids: string[]) => void;
  onSelectCollection: (id: string) => void;
  onSelectConnector: (id: string) => void;
  onSelectService: (skuSelectionId: string, containingCollectionId: string) => void;
  onDeselectAll: () => void;
  onCreateConnector: (from: string, to: string) => void;
  onUpdateCollectionParent: (id: string, parentId: string | null) => void;
  /** 010-multi-region-support, spec FR-004: called instead of `onUpdateCollectionParent` when
   * a drag targets a VPC in a different region than the dragged Application — no API call is
   * made; the caller surfaces this as a visible message (research.md §8: no prior rejection
   * pattern existed in this flow). */
  onRejectedNesting: (applicationName: string, vpcName: string) => void;
  /** 016-canvas-icon-layout, FR-004a: an icon was dropped into another box in the same region
   * — move that service there. Rejects if the move fails (the icon then returns). */
  onMoveService: (skuSelectionId: string, targetCollectionId: string) => Promise<void>;
  /** 016-canvas-icon-layout, FR-004b: an icon was dropped into a box in another region; nothing
   * moves, and this explains why (shown in column 2). */
  onMoveRejected: (message: string) => void;
  /** 009-ui-fixes-next-iteration follow-up: a fresh Architecture refetch, for the new manual
   * refresh button (a temporary workaround for the still-not-root-caused "diagram goes
   * blank" issue — US3/research.md §3's investigation, and this session's own `diagramSelection`
   * memoization fix, found *a* real contributing mechanism but evidently not the only one, per
   * this user's continued live reports) — `WorkspacePage.tsx` owns the query, this panel only
   * triggers it and separately forces its own React Flow instance to fully remount. */
  onRefresh: () => void;
  /** 011-canvas-connector-popout, spec FR-007: opens `PopoutCanvasDialog`
   * (`WorkspacePage.tsx`), a second, independent instance of this same panel enlarged in an
   * in-tab overlay — this panel only triggers it, `WorkspacePage.tsx` owns the open/closed
   * state since the trigger (here) and the dialog itself are siblings, not parent/child.
   * Optional and omitted by `PopoutCanvasDialog` itself when it renders this same panel a
   * second time inside the pop-out — that instance has no nested pop-out affordance of its
   * own (there's nothing further to pop out to), so the trigger button doesn't render there. */
  onOpenPopout?: () => void;
  /** 011-canvas-connector-popout follow-up, live user report: with this panel's `<ReactFlow>`
   * left unkeyed, `@xyflow/react` defaults its internal `rfId` to the *same* static `'1'` for
   * every instance (confirmed in `node_modules/@xyflow/react`'s own source: `const rfId = id ||
   * '1'`) — since SVG marker ids are derived purely from `rfId` + the marker's own properties
   * (`getMarkerId`), column 4's panel and `PopoutCanvasDialog`'s second instance rendered
   * `<marker id="...">` elements with byte-for-byte identical ids while the pop-out was open.
   * `id` attributes must be document-unique; closing the pop-out removed whichever `<defs>` the
   * browser had actually been resolving `url(#id)` references to, silently blanking column 4's
   * arrows until a full refresh recreated a single consistent tree. Defaults to `"main"` so
   * every pre-existing caller (just column 4 itself) keeps working without a prop; only
   * `PopoutCanvasDialog` passes a different value. */
  instanceId?: string;
}

/**
 * Column 4: the assembled architecture diagram (007-ui-overhaul-shadcn, FR-006). The React
 * Flow canvas itself, relocated verbatim from the pre-007 `CreateArchitecturePage` (002-006),
 * plus FR-014's new per-service click target. All state this panel needs to *own* elsewhere
 * (which Collection/Connector/service is selected, the measured-height map) lives in
 * `WorkspacePage` and is threaded through as props — this panel only owns the React Flow
 * node/edge view state itself (`useNodesState`/`useEdgesState`), which is inherently local to
 * the canvas rendering, not cross-panel application state.
 */
export function ArchitectureDiagramPanel({
  architectureId,
  collections,
  connectors,
  ownHeights,
  reportHeight,
  diagramSelection,
  onSelectedNodeIdsChange,
  onSelectCollection,
  onSelectConnector,
  onSelectService,
  onDeselectAll,
  onCreateConnector,
  onUpdateCollectionParent,
  onRejectedNesting,
  onMoveService,
  onMoveRejected,
  onRefresh,
  onOpenPopout,
  instanceId = "main",
}: ArchitectureDiagramPanelProps) {
  const { getIntersectingNodes, getNodes, screenToFlowPosition } = useReactFlow();

  // 009-ui-fixes-next-iteration follow-up: bumped by the new refresh button to force
  // `<ReactFlow>` below to fully remount (its `key` includes this) even though
  // `architectureId` hasn't changed — a full reset of React Flow's own internal state, the
  // same "start over from nothing" a page reload gives it, without an actual page reload.
  const [remountNonce, setRemountNonce] = useState(0);

  // 009-ui-fixes-next-iteration follow-up: zoom level now survives a reload, per-browser
  // per-Architecture (`lib/diagramViewport.ts`, modeled on `diagramLayout.ts`). `<ReactFlow>`
  // only reads `defaultViewport` once, at mount — keyed below by `architectureId` so
  // switching Architectures (which doesn't itself remount this component — same precedent as
  // `manualSizeRef`'s reseeding above) gets a fresh, correctly-restored zoom instead of
  // inheriting whatever the previously-open Architecture's zoom happened to be. Pan position
  // is deliberately not persisted (not asked for, and restoring an old pan offset without
  // also restoring exactly which Collections existed then would be more disorienting than
  // useful) — every restore re-centers at x:0, y:0.
  const defaultViewport = useMemo<Viewport>(
    () => ({ x: 0, y: 0, zoom: readDiagramZoom(architectureId) ?? DEFAULT_DIAGRAM_ZOOM }),
    [architectureId],
  );
  const onMoveEnd = useCallback(
    (_event: MouseEvent | TouchEvent | null, viewport: Viewport) => {
      writeDiagramZoom(architectureId, viewport.zoom);
    },
    [architectureId],
  );
  // Live percentage for the on-canvas readout below (FR: column 4 zoom %) — `useViewport()`
  // is the reactive/subscribing counterpart to `useReactFlow()`'s one-shot `getViewport()`,
  // so this re-renders as the user zooms rather than only reflecting the value as of the last
  // unrelated render.
  const viewport = useViewport();
  const currentZoom = viewport.zoom;

  // 009-ui-fixes-next-iteration follow-up: the outer panel's own height, now real React
  // state driving `DiagramResizeHandle` below — see that component's own comment for why a
  // hardcoded `style={{ height: 640 }}` (the prior approach) silently discarded a user's
  // resize on the very next unrelated re-render. Not persisted (never was, even under the
  // old native-resize approach) — in scope here is fixing the interaction, not adding new
  // scope.
  const [diagramHeight, setDiagramHeight] = useState(640);

  // 010-multi-region-support, spec FR-008: React Flow's own `selectedNodes` array is in its
  // internal node-array order, not click order — track click order ourselves so "first
  // selected = from, second selected = to" (the column-2 connect flow, WorkspacePage.tsx's
  // `handleConnect`) is actually correct rather than incidentally matching diagram order.
  const orderedSelectedIdsRef = useRef<string[]>([]);
  useOnSelectionChange({
    onChange: ({ nodes: selectedNodes }) => {
      const next = updateOrderedSelection(
        orderedSelectedIdsRef.current,
        selectedNodes.map((n) => n.id),
      );
      orderedSelectedIdsRef.current = next;
      onSelectedNodeIdsChange(next);
    },
  });

  // A user's drag-to-resize (FR-001, research.md §1a — root cause of "resize doesn't
  // stick"): `initialNodes` below recomputes, and gets re-applied via the `useEffect`
  // further down, whenever *any* box's content height changes — not just the box being
  // resized — which previously reset every box's `style.width`/`style.height` back to its
  // auto-computed value on every such recompute, silently discarding whatever the user just
  // dragged. A plain ref (not state) is enough here: it doesn't itself need to trigger a
  // recompute when a resize happens — `onNodesChange`/`applyNodeChanges` already keeps the
  // *live* `nodes` state showing the just-applied resize in the moment; this ref only needs
  // to be read the *next* time `initialNodes` recomputes for some unrelated reason, so that
  // recompute preserves a manually-set size instead of overwriting it.
  // 009-ui-fixes-next-iteration, US7, FR-024: now also carries `x`/`y` (previously just
  // `width`/`height`) and is seeded from `diagramLayout.ts`'s per-Architecture `localStorage`
  // persistence — new, not a reuse of an existing mechanism (research.md §7a corrects an
  // earlier wrong assumption that 005/007/008 already persisted this across reloads; they
  // only ever kept it in-memory for the current session). Reseeded synchronously in the render
  // body (not an effect) whenever `architectureId` changes, so the very first `initialNodes`
  // compute for a newly-opened Architecture already reflects its stored layout.
  const manualSizeRef = useRef<Map<string, CollectionLayoutOverride>>(new Map());
  const lastArchitectureIdRef = useRef<string | null>(null);
  if (lastArchitectureIdRef.current !== architectureId) {
    lastArchitectureIdRef.current = architectureId;
    manualSizeRef.current = new Map(Object.entries(readDiagramLayout(architectureId)));
  }
  // 016-canvas-icon-layout, FR-013: a top-level box created while this Architecture is open is
  // placed inside the part of the canvas the user is looking at (clear of other boxes where
  // there's room), rather than the next slot of the fixed grid — which could be off-screen.
  // Boxes present when the Architecture opens keep today's placement. The chosen spot is saved
  // like a manual move, so it survives a reload. Runs in the render body, like the reseed
  // above, so the very first `initialNodes` for the new box already uses it.
  const canvasRef = useRef<HTMLDivElement>(null);
  const seenTopLevelRef = useRef<{ architectureId: string; ids: Set<string> } | null>(null);
  const topLevelCollections = collections.filter((c) => !c.parent_collection_id);
  if (seenTopLevelRef.current?.architectureId !== architectureId) {
    seenTopLevelRef.current = {
      architectureId,
      ids: new Set(topLevelCollections.map((c) => c.id)),
    };
  } else {
    const seen = seenTopLevelRef.current.ids;
    for (const c of topLevelCollections) {
      if (seen.has(c.id)) continue;
      seen.add(c.id);
      const canvas = canvasRef.current;
      if (manualSizeRef.current.has(c.id) || !canvas) continue;
      const zoom = viewport.zoom || 1;
      const visible: PlacementRect = {
        x: -viewport.x / zoom,
        y: -viewport.y / zoom,
        width: canvas.clientWidth / zoom,
        height: canvas.clientHeight / zoom,
      };
      const occupied: PlacementRect[] = getNodes()
        .filter((n) => !n.parentId)
        .map((n) => ({
          x: n.position.x,
          y: n.position.y,
          width: n.measured?.width ?? n.width ?? 0,
          height: n.measured?.height ?? n.height ?? 0,
        }));
      const size = {
        width: defaultBoxWidth(
          c.sku_selections.length,
          c.type === "vpc" ? VPC_MIN_WIDTH : APPLICATION_MIN_WIDTH,
        ),
        height: estimateComponentHeight(c.sku_selections.length),
      };
      const slot = findVisibleSlot(visible, occupied, size);
      const layout: CollectionLayoutOverride = slot;
      manualSizeRef.current.set(c.id, layout);
      writeCollectionLayout(architectureId, c.id, layout);
    }
  }

  // Shared by both the resize control (which reports width/height/x/y together) and
  // `onNodeDragStop` below (which reports a move — see there for how it fills in width/height
  // from the node's own current size rather than guessing).
  const onManualResize = useCallback(
    (id: string, width: number, height: number, x: number, y: number) => {
      const layout: CollectionLayoutOverride = { width, height, x, y };
      manualSizeRef.current.set(id, layout);
      writeCollectionLayout(architectureId, id, layout);
    },
    [architectureId],
  );

  // 016-canvas-icon-layout, FR-004–FR-006: this Architecture's hand-placed icon positions
  // (per browser), re-read when the Architecture changes and updated after each drop.
  const [iconLayout, setIconLayout] = useState<IconPositions>(() => readIconLayout(architectureId));
  const iconLayoutArchitectureRef = useRef(architectureId);
  if (iconLayoutArchitectureRef.current !== architectureId) {
    iconLayoutArchitectureRef.current = architectureId;
    setIconLayout(readIconLayout(architectureId));
  }

  /** Where an icon dropped at `clientX/clientY` lands inside box `node`'s icon area — the
   * nearest spot that keeps its spacing from the box's other icons (FR-005). */
  const iconSpotIn = useCallback(
    (node: Node, absolute: { x: number; y: number }, point: { x: number; y: number }, selectionId: string) => {
      const data = node.data as unknown as { boxWidth: number; skuSelections: Collection["sku_selections"] };
      const innerWidth = innerWidthOf(data.boxWidth);
      const others = Object.entries(
        resolvePositions(
          data.skuSelections.map((sel) => sel.id),
          iconLayout,
          innerWidth,
        ),
      )
        .filter(([id]) => id !== selectionId)
        .map(([, pos]) => pos);
      const inset = PAD + BORDER / 2;
      const drop = {
        x: point.x - absolute.x - inset - ICON / 2,
        y: point.y - absolute.y - inset - ICON_AREA_TOP - ICON / 2,
      };
      return nearestValidSpot(drop, others, { width: innerWidth });
    },
    [iconLayout],
  );

  const onIconDrop = useCallback(
    async (selectionId: string, sourceCollectionId: string, clientX: number, clientY: number) => {
      const point = screenToFlowPosition({ x: clientX, y: clientY });
      const nodes = getNodes();
      const byId = new Map(nodes.map((n) => [n.id, n]));
      const absoluteOf = (n: Node) => {
        const parent = n.parentId ? byId.get(n.parentId) : undefined;
        return parent
          ? { x: parent.position.x + n.position.x, y: parent.position.y + n.position.y }
          : n.position;
      };
      const regionById = new Map(collections.map((c) => [c.id, c.region]));
      const boxes: DropBox[] = nodes
        .filter((n) => regionById.has(n.id))
        .map((n) => ({
          id: n.id,
          parentId: n.parentId,
          region: regionById.get(n.id)!,
          rect: {
            ...absoluteOf(n),
            width: n.measured?.width ?? n.width ?? 0,
            height: n.measured?.height ?? n.height ?? 0,
          },
        }));
      const decision = decideIconDrop({ point, boxes, sourceId: sourceCollectionId });
      if (decision.kind === "none") return; // empty canvas: the icon stays where it was
      if (decision.kind === "reject-region") {
        const selection = collections
          .find((c) => c.id === sourceCollectionId)
          ?.sku_selections.find((sel) => sel.id === selectionId);
        onMoveRejected(
          `"${selection?.service_code ?? "This service"}" can only move to a box in ${decision.sourceRegion}.`,
        );
        return;
      }
      const target = byId.get(decision.targetId);
      if (!target) return;

      const spot = iconSpotIn(target, absoluteOf(target), point, selectionId);
      const previous = iconLayout[selectionId];
      // Pin every other icon in the boxes involved where it is now, so moving one icon never
      // re-flows the ones that were still in default placement (FR-008).
      const pinned: IconPositions = {};
      for (const boxId of new Set([sourceCollectionId, target.id])) {
        const box = byId.get(boxId);
        if (!box) continue;
        const data = box.data as unknown as {
          boxWidth: number;
          skuSelections: Collection["sku_selections"];
        };
        const current = resolvePositions(
          data.skuSelections.map((sel) => sel.id),
          iconLayout,
          innerWidthOf(data.boxWidth),
        );
        for (const [id, pos] of Object.entries(current)) if (id !== selectionId) pinned[id] = pos;
      }
      writeIconPositions(architectureId, { ...pinned, [selectionId]: spot });
      setIconLayout((prev) => ({ ...prev, ...pinned, [selectionId]: spot }));
      if (target.id === sourceCollectionId) return;

      try {
        await onMoveService(selectionId, target.id);
      } catch {
        // The move failed (the error shows in column 2) — put the icon back where it was.
        if (previous) writeIconPosition(architectureId, selectionId, previous);
        else removeIconPosition(architectureId, selectionId);
        setIconLayout(readIconLayout(architectureId));
      }
    },
    [
      screenToFlowPosition,
      getNodes,
      collections,
      onMoveRejected,
      onMoveService,
      iconSpotIn,
      iconLayout,
      architectureId,
    ],
  );

  const selectedServiceId =
    diagramSelection?.kind === "service" ? diagramSelection.id : undefined;

  const initialNodes: Node[] = useMemo(() => {
    const topLevel = collections.filter((c) => !c.parent_collection_id);
    const childrenByParent = new Map<string, Collection[]>();
    for (const c of collections) {
      if (c.parent_collection_id) {
        const list = childrenByParent.get(c.parent_collection_id) ?? [];
        list.push(c);
        childrenByParent.set(c.parent_collection_id, list);
      }
    }

    function toLayoutNode(c: Collection): MeasuredLayoutNode {
      return {
        id: c.id,
        ownServiceCount: c.sku_selections.length,
        children: (childrenByParent.get(c.id) ?? []).map(toLayoutNode),
      };
    }

    const nodes: Node[] = [];
    const placeInGrid = flowGridPlacer();
    topLevel.forEach((c) => {
      const children = c.type === "vpc" ? (childrenByParent.get(c.id) ?? []) : [];
      // 016-canvas-icon-layout, FR-002: wide enough for up to 3 icons per row, never narrower
      // than today's default — and a VPC also fits its widest nested box plus that box's inset.
      const childWidths = children.map(
        (child) =>
          manualSizeRef.current.get(child.id)?.width ??
          defaultBoxWidth(child.sku_selections.length, NESTED_APPLICATION_MIN_WIDTH),
      );
      const width = Math.max(
        defaultBoxWidth(
          c.sku_selections.length,
          c.type === "vpc" ? VPC_MIN_WIDTH : APPLICATION_MIN_WIDTH,
        ),
        ...childWidths.map((w) => w + 2 * NESTED_CHILD_INSET),
      );
      const layoutNode = toLayoutNode(c);
      const height = computeMeasuredHeight(layoutNode, ownHeights);
      // A manual override's height is clamped to never go *below* the current auto-fit
      // height, so content added after a manual shrink still can't end up clipped again
      // (FR-002 stays satisfied even for a box the user has resized, FR-001's own resize
      // still wins whenever the user has sized it *taller* than auto-fit would).
      const manualSize = manualSizeRef.current.get(c.id);
      // A manual width is kept, but never below one icon's worth (spec Edge Cases).
      const finalWidth = manualSize ? Math.max(manualSize.width, MIN_ICON_BOX_WIDTH) : width;
      const finalHeight = manualSize ? Math.max(manualSize.height, height) : height;
      // 009-ui-fixes-next-iteration, US7, FR-024: a stored position overrides the computed
      // grid slot — only meaningful for top-level Collections (nested children are always
      // auto-stacked within their parent via `childYOffsets` below, unrelated to this).
      // 009-ui-fixes-next-iteration, US7, FR-023: grid spacing increased from 008's 260/220.
      // 016-canvas-icon-layout: boxes are now as wide as their icons need (FR-002) and as tall
      // as their rows of 60px icons, so a fixed 300×260 grid made default-placed boxes overlap.
      // Default slots now flow left to right by each box's real width, 4 per row, each row
      // starting below the tallest box of the one before — with the same 80/40 gaps as before
      // (`flowGridPlacer`, newNodePlacement.ts).
      const slot = placeInGrid({ width: finalWidth, height: finalHeight });
      const finalX = manualSize?.x ?? slot.x;
      const finalY = manualSize?.y ?? slot.y;
      nodes.push({
        id: c.id,
        type: c.type === "vpc" ? "vpc" : "applicationComponent",
        position: { x: finalX, y: finalY },
        data: {
          // 009-ui-fixes-next-iteration, US7, FR-017: no longer appends "(${c.type})" — the
          // collection type is redundant visual clutter, per spec.
          label: c.name,
          skuSelections: c.sku_selections,
          minHeight: height,
          isSelected: diagramSelection?.kind === "collection" && diagramSelection.id === c.id,
          selectedServiceId,
          onMeasuredHeight: (h: number) => reportHeight(c.id, h),
          onSelectService: (skuSelectionId: string) => onSelectService(skuSelectionId, c.id),
          onManualResize: (w: number, h: number, x: number, y: number) =>
            onManualResize(c.id, w, h, x, y),
          // 009-ui-fixes-next-iteration follow-up: only meaningful for `VpcNode` (see
          // `VpcNodeData`/`ServiceList`'s `hideEmptyMessage`) — harmlessly unused by
          // `ApplicationComponentNode`, which can never have children.
          hasChildren: children.length > 0,
          region: c.region,
          isNested: false,
          boxWidth: finalWidth,
          savedPositions: iconLayout,
          onIconDrop: (selectionId: string, x: number, y: number) =>
            void onIconDrop(selectionId, c.id, x, y),
        },
        style: { width: finalWidth, height: finalHeight },
      });
      const offsets = childYOffsets(layoutNode, ownHeights);
      children.forEach((child) => {
        const childLayoutNode = toLayoutNode(child);
        const childHeight = computeMeasuredHeight(childLayoutNode, ownHeights);
        const childManualSize = manualSizeRef.current.get(child.id);
        const childFinalWidth = childManualSize
          ? Math.max(childManualSize.width, MIN_ICON_BOX_WIDTH)
          : defaultBoxWidth(child.sku_selections.length, NESTED_APPLICATION_MIN_WIDTH);
        const childFinalHeight = childManualSize
          ? Math.max(childManualSize.height, childHeight)
          : childHeight;
        nodes.push({
          id: child.id,
          type: "applicationComponent",
          parentId: c.id,
          position: { x: 20, y: offsets[child.id] },
          data: {
            label: child.name,
            skuSelections: child.sku_selections,
            minHeight: childHeight,
            isSelected:
              diagramSelection?.kind === "collection" && diagramSelection.id === child.id,
            selectedServiceId,
            onMeasuredHeight: (h: number) => reportHeight(child.id, h),
            onSelectService: (skuSelectionId: string) =>
              onSelectService(skuSelectionId, child.id),
            onManualResize: (w: number, h: number, x: number, y: number) =>
              onManualResize(child.id, w, h, x, y),
            region: child.region,
            isNested: true,
            boxWidth: childFinalWidth,
            savedPositions: iconLayout,
            onIconDrop: (selectionId: string, x: number, y: number) =>
              void onIconDrop(selectionId, child.id, x, y),
          },
          style: { width: childFinalWidth, height: childFinalHeight },
        });
      });
    });
    return nodes;
  }, [
    collections,
    ownHeights,
    reportHeight,
    onSelectService,
    onManualResize,
    diagramSelection,
    selectedServiceId,
    iconLayout,
    onIconDrop,
  ]);

  // 009-ui-fixes-next-iteration, US4, FR-010: multiple Connectors between the same pair of
  // Collections would otherwise render exactly on top of each other (React Flow's default for
  // edges sharing a source/target) — offset each one's bezier curvature by its index within its
  // own pair group so they render as distinct, independently clickable paths.
  //
  // Deliberately reads `initialNodes` from closure rather than listing it as a dependency
  // (009-ui-fixes-next-iteration follow-up, new arch spec requirement) — same pattern as
  // `manualSizeRef`'s reads elsewhere in this file. `resolveConnectorSides` only actually
  // *needs* current geometry for a Connector that doesn't have a persisted side yet; making
  // this recompute (and re-derive `sourceHandle`/`targetHandle` for every edge) on every
  // content-driven relayout would be wasteful and, worse, could make an *already-resolved*
  // Connector's rendered side flicker against its own persisted value for one frame on an
  // unrelated box's height changing — this only needs to run when `connectors` itself changes.
  const initialEdges: Edge[] = useMemo(() => {
    const { resolved } = resolveConnectorSides(
      connectors,
      initialNodes,
      readConnectorSides(architectureId),
    );
    const rawEdges = connectors.map((conn) => {
      const isSelected = diagramSelection?.kind === "connector" && diagramSelection.id === conn.id;
      // 009-ui-fixes-next-iteration, US9 follow-up: same `awsDataTransferLabel()` derivation
      // as `ServiceList`/`PricingPanel` — found live (via user report) that this edge label
      // was the one place FR-028's "everywhere that SKU is shown" wiring missed, since FR-028
      // only literally named columns 2/4/5 and this is a Connector's own label, not a
      // Collection's. A Connector-attached AWSDataTransfer Service was reading as "not in the
      // diagram at all" — technically rendered, but as a bare, unrecognizable raw SKU id at
      // `text-4xs` on a thin line, easy to mistake for empty/decorative.
      const dataTransferLabel = conn.sku_selection
        ? awsDataTransferLabel(conn.sku_selection.service_code, conn.sku_selection.attributes)
        : null;
      const sides = resolved.get(conn.id);
      return {
        id: conn.id,
        source: conn.from_collection_id,
        target: conn.to_collection_id,
        // 009-ui-fixes-next-iteration follow-up, new arch spec requirement: which of the
        // source/target box's four `SideHandles` this Connector attaches to —
        // `resolveConnectorSides` above (persisted choice, or freshly auto-routed for a
        // brand-new Connector). `undefined` (React Flow's own single-default-handle
        // fallback) only if geometry genuinely couldn't be resolved (a missing node — should
        // never happen; see that function's own comment).
        sourceHandle: sides?.from,
        targetHandle: sides?.to,
        // Lets the user grab either end of an already-drawn Connector and drag it to a
        // different side (the other half of the same requirement) — `onReconnect` below is
        // what actually applies and persists the change.
        reconnectable: true,
        // 009-ui-fixes-next-iteration, US7, FR-022/FR-025: three-step-reduced font, underlined
        // when this Connector is the current selection.
        //
        // Found live (US9 follow-up, same investigation): `BaseEdge`'s `label` renders via
        // React Flow's own `EdgeText`, which places `label` directly inside an SVG `<text>`
        // element and measures it with `getBBox()` to decide when to reveal it — nesting an
        // HTML `<span>` there (the previous approach, for the `text-4xs`/`underline` Tailwind
        // classes) isn't valid SVG content, so the browser never lays it out: `getBBox()` keeps
        // returning a zero-width box forever, and `EdgeText` stays permanently
        // `visibility: hidden` as a result (confirmed live: the label's DOM text content was
        // present and correct, but nothing ever painted). A Connector's attached Service was
        // therefore invisible on the diagram even before this session's `awsDataTransferLabel`
        // fix — not just unreadable. Fixed by passing a plain string plus `labelStyle` (an
        // inline style object, which `BaseEdge` does support) instead of a styled element.
        label: conn.sku_selection ? dataTransferLabel ?? conn.sku_selection.sku : undefined,
        labelStyle: { fontSize: "var(--text-2xs)", textDecoration: isSelected ? "underline" : "none" },
        // 010-multi-region-support, spec FR-009: a directional arrow pointing from "from" to
        // "to" — `OffsetEdge` already forwards `markerEnd` to `<BaseEdge>` (it just never had a
        // value before this). `width`/`height` 3x React Flow's own default (12.5) per live user
        // request — the default read as too small against this diagram's box sizes.
        markerEnd: { type: MarkerType.ArrowClosed, width: 37.5, height: 37.5 },
      };
    });
    const offsets = edgeOffsetIndex(rawEdges);
    return rawEdges.map((edge) => ({
      ...edge,
      type: "offset",
      // `architectureId`: `OffsetEdge` needs it to read/write this Connector's manual bend
      // (`connectorBends.ts`) — threaded through `data` since it's a top-level function
      // component, not a closure inside this panel, and `EdgeProps` has no prop for it.
      // `isSelected`: found live — this app never sets React Flow's own `edge.selected` (only
      // nodes get that treatment, below), so `EdgeProps.selected` is always false for a
      // Connector; the bend handle needs `data.isSelected` instead, recomputed the same way
      // the label's underline (`isSelected` above, scoped to the other `.map` this one can't
      // see into) already is — matching how the sidebar's own "Selected Collection" already
      // reflects `diagramSelection`.
      data: {
        offsetIndex: offsets[edge.id] ?? 0,
        architectureId,
        isSelected: diagramSelection?.kind === "connector" && diagramSelection.id === edge.id,
      },
    }));
  }, [connectors, diagramSelection, architectureId]);

  // Persists whichever Connectors `initialEdges` above just had to freshly auto-route (no
  // stored side yet) — kept as its own effect, not inline in that `useMemo`, so a render
  // never has the side effect of writing to `localStorage` (009-ui-fixes-next-iteration
  // follow-up, new arch spec requirement). Recomputes the exact same resolution `initialEdges`
  // just used (deterministic given the same `connectors`/`initialNodes`/persisted-sides
  // inputs, so it can never disagree with what was actually rendered) purely to find which
  // entries are new, then writes only those.
  useEffect(() => {
    const { newlyComputed } = resolveConnectorSides(
      connectors,
      initialNodes,
      readConnectorSides(architectureId),
    );
    for (const [connectorId, sides] of newlyComputed) {
      writeConnectorSides(architectureId, connectorId, sides);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `initialNodes` deliberately
    // read from closure, not listed; see `initialEdges`'s own comment above for why.
  }, [connectors, architectureId]);

  const [nodes, setNodes, rawOnNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, rawOnEdgesChange] = useEdgesState(initialEdges);

  // Found live (008, FR-001): `initialNodes` never sets `selected` at all, so blindly
  // replacing `nodes` with it on every recompute was also silently clearing React Flow's own
  // selection state — not just the manually-resized dimensions T003's `manualSizeRef` above
  // already fixes. Since `initialNodes` recomputes on *any* box's content changing (the same
  // "clobbering" pattern as the resize bug), a user's click-to-select was being wiped again
  // within the same render pass it was set in, before `<NodeResizer isVisible={selected}>`
  // ever got a chance to actually show its handles — which is why manual resize "didn't
  // work" even after both other fixes above: there was never a visible, clickable handle to
  // grab in the first place. Preserve which node ids were selected in the *current* `nodes`
  // state and reapply that flag to the freshly-built `initialNodes`, instead of discarding it.
  useEffect(() => {
    setNodes((current) => {
      const selectedIds = new Set(current.filter((n) => n.selected).map((n) => n.id));
      if (selectedIds.size === 0) return initialNodes;
      return initialNodes.map((n) => (selectedIds.has(n.id) ? { ...n, selected: true } : n));
    });
  }, [initialNodes, setNodes]);
  useEffect(() => setEdges(initialEdges), [initialEdges, setEdges]);

  function onConnect(connection: Connection) {
    if (!connection.source || !connection.target) return;
    onCreateConnector(connection.source, connection.target);
    setEdges((eds) => addEdge(connection, eds));
  }

  // 009-ui-fixes-next-iteration follow-up, new arch spec requirement: dragging an existing
  // Connector's endpoint to a different side of the same (or a different) box. React Flow
  // calls this once the drag completes on a valid `reconnectable` edge (set per-edge in
  // `initialEdges` above) — `newConnection.sourceHandle`/`targetHandle` are the side ids
  // (`"top"`/`"right"`/`"bottom"`/`"left"`) of wherever the user actually dropped it, which
  // is the user's own explicit, deliberate choice — no `chooseConnectorSides` auto-routing
  // applies here, only to a brand-new Connector's *initial* placement. Persisted immediately,
  // exactly as if that side had been the connector's original one, so it stays put across a
  // reload (and correctly counts toward that box's per-side usage for any *other* Connector
  // auto-routed afterward).
  const onReconnect = useCallback(
    (oldEdge: Edge, newConnection: Connection) => {
      setEdges((eds) => reconnectEdge(oldEdge, newConnection, eds));
      if (
        !isConnectorSide(newConnection.sourceHandle) ||
        !isConnectorSide(newConnection.targetHandle)
      ) {
        return;
      }
      writeConnectorSides(architectureId, oldEdge.id, {
        from: newConnection.sourceHandle,
        to: newConnection.targetHandle,
      });
    },
    [architectureId, setEdges],
  );

  const onNodeDragStop = (_event: MouseEvent | TouchEvent, node: Node) => {
    const dragged = collections.find((c) => c.id === node.id);
    if (!dragged) return;

    // 009-ui-fixes-next-iteration, US7, FR-024: persist the new position for a top-level
    // Collection (both types — VPC and Application Component) — nested children stay
    // auto-stacked within their parent (`childYOffsets` above), so their position isn't a
    // meaningful, independently-persistable thing to drag. Width/height come from whatever
    // this node's current size already is (an unrelated prior resize, or its computed
    // default) — a plain move never changes size, so there's nothing new to measure here.
    if (!dragged.parent_collection_id) {
      const width = node.width ?? node.measured?.width ?? manualSizeRef.current.get(node.id)?.width ?? 0;
      const height =
        node.height ?? node.measured?.height ?? manualSizeRef.current.get(node.id)?.height ?? 0;
      onManualResize(node.id, width, height, node.position.x, node.position.y);
    }

    if (dragged.type !== "application_component") return;

    const intersectingVpcIds = getIntersectingNodes(node)
      .filter((n) => collections.find((c) => c.id === n.id)?.type === "vpc")
      .map((n) => n.id);

    // 010-multi-region-support, spec FR-004: same-region nesting only.
    const vpcRegions = Object.fromEntries(
      collections.filter((c) => c.type === "vpc").map((c) => [c.id, c.region]),
    );
    const { changed, newParentId, rejected, rejectedVpcId } = decideNestingChange(
      intersectingVpcIds,
      dragged.parent_collection_id ?? null,
      dragged.region,
      vpcRegions,
    );
    if (rejected) {
      const vpcName = collections.find((c) => c.id === rejectedVpcId)?.name ?? "that VPC";
      onRejectedNesting(dragged.name, vpcName);
      return;
    }
    if (changed) {
      onUpdateCollectionParent(dragged.id, newParentId);

      // Found live (user report): without this, the dropped box just stayed wherever the
      // cursor released it — possibly still hanging outside the VPC's own border — until the
      // save request round-tripped and `architecture` refetched, at which point `initialNodes`
      // recomputed and it visually snapped into its real stacked slot. Reads as "doesn't snap
      // into the VPC" even though the nesting itself was saved correctly the whole time.
      // Scoped to nesting *into* a VPC (the reported case) — un-nesting back out still relies
      // on the same refetch-driven recompute as before, unchanged.
      if (newParentId !== null) {
        const parentCollection = collections.find((c) => c.id === newParentId);
        if (parentCollection) {
          const existingSiblings = collections.filter(
            (c) => c.parent_collection_id === newParentId && c.id !== dragged.id,
          );
          const layoutNode: MeasuredLayoutNode = {
            id: parentCollection.id,
            ownServiceCount: parentCollection.sku_selections.length,
            children: [
              ...existingSiblings.map((s) => ({
                id: s.id,
                ownServiceCount: s.sku_selections.length,
                children: [],
              })),
              { id: dragged.id, ownServiceCount: dragged.sku_selections.length, children: [] },
            ],
          };
          const offsets = childYOffsets(layoutNode, ownHeights);
          // The dragged node repositioning correctly (confirmed live via its DOM transform)
          // wasn't the whole story: it's positioned *relative to* the VPC's own box, whose
          // rendered height was still the pre-nesting one at this exact instant — so the
          // child visibly spilled past the VPC's still-stale bottom border until the real
          // refetch also grew the VPC. Grow the VPC node's own height here too, the same
          // manual-override-aware rule `initialNodes` itself uses, so both update together.
          const requiredParentHeight = computeMeasuredHeight(layoutNode, ownHeights);
          const parentManualSize = manualSizeRef.current.get(newParentId);
          const parentFinalHeight = parentManualSize
            ? Math.max(parentManualSize.height, requiredParentHeight)
            : requiredParentHeight;
          setNodes((current) =>
            current.map((n) => {
              if (n.id === dragged.id) {
                return { ...n, parentId: newParentId, position: { x: 20, y: offsets[dragged.id] } };
              }
              if (n.id === newParentId) {
                return { ...n, style: { ...n.style, height: parentFinalHeight } };
              }
              return n;
            }),
          );
        }
      }
    }
  };

  // FR-003 (008-ui-updates-corrections): a defensive mitigation, not a confirmed root-cause
  // fix — research.md §1c documents that the exact trigger for "clicking empty VPC space
  // makes the whole diagram disappear, needing a reload" could not be reproduced live
  // (5 attempts) to get a definitive stack trace. One well-supported hypothesis survives
  // static review: an exception thrown inside one of these event-handler callbacks (not the
  // render phase) would NOT be caught by `frontend/src/components/ErrorBoundary.tsx` — React
  // error boundaries only catch render/lifecycle errors, not event-handler errors — leaving
  // whatever partial state update was interrupted in place instead of a clean fallback UI.
  // This wrapper makes that specific failure mode impossible regardless of what the real
  // trigger turns out to be: any exception here is caught, logged, and the diagram stays
  // interactive rather than silently breaking. If the user's real trigger is this, this fix
  // resolves it directly; if it's the other standing hypothesis (viewport/pan-zoom
  // corruption, not a thrown error), this wrapper is a no-op safety net and the underlying
  // issue still needs its own fix — flagged for the user to confirm against their own exact
  // repro, which this tool could not reproduce to verify against directly.
  function safely<Args extends unknown[]>(fn: (...args: Args) => void): (...args: Args) => void {
    return (...args: Args) => {
      try {
        fn(...args);
      } catch (err) {
        console.error(
          "[ArchitectureDiagramPanel] caught an error in a diagram event handler — the " +
            "diagram stays interactive instead of leaving a partially-updated view (FR-003):",
          err,
        );
      }
    };
  }

  const onNodesChange = safely(rawOnNodesChange);
  const onEdgesChange = safely(rawOnEdgesChange);
  const safeOnConnect = safely(onConnect);
  const safeOnNodeDragStop = safely(onNodeDragStop);
  const safeOnNodeClick = safely((_: unknown, node: Node) => onSelectCollection(node.id));
  const safeOnEdgeClick = safely((_: unknown, edge: Edge) => onSelectConnector(edge.id));
  const safeOnPaneClick = safely(onDeselectAll);
  const safeOnReconnect = safely(onReconnect);

  return (
    <div
      // FR-004 (008): raised from the prior 320px default / 320px min-height ceiling (005) —
      // "substantially more of the window's available height" per spec; still fully
      // user-resizable, now via `DiagramResizeHandle` below rather than the native CSS
      // `resize-y` this replaced (see that component's own comment for why), with no
      // artificial max-height capping how much further the user can drag it.
      ref={canvasRef}
      className="relative h-full overflow-auto rounded border border-border bg-muted/20"
      style={{ height: diagramHeight }}
    >
      <ReactFlow
        // Keyed by `architectureId` (see the comment above `defaultViewport`) so switching
        // Architectures gets a genuinely fresh pan-zoom instance — `defaultViewport` is only
        // ever read once, at mount, and this component doesn't otherwise remount on its own.
        // `remountNonce` is the same idea, manually triggered by the refresh button.
        key={`${architectureId}-${remountNonce}`}
        // `id` (see `instanceId`'s own doc comment on `ArchitectureDiagramPanelProps`): without
        // this, two simultaneously-mounted instances (column 4 + the pop-out) generate
        // colliding SVG marker ids.
        id={instanceId}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        attributionPosition="bottom-left"
        defaultViewport={defaultViewport}
        onMoveEnd={onMoveEnd}
        // 009-ui-fixes-next-iteration follow-up, new arch spec requirement: lets a drag
        // start from (or land on) any of `SideHandles`' four per-side handles regardless of
        // whether that particular one is the `source`- or `target`-typed sibling at that
        // position — without this, `connectionMode`'s default ("strict") would only allow
        // dragging *from* a `source` handle *to* a `target` handle, defeating the point of
        // having both at every side.
        connectionMode={ConnectionMode.Loose}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={safeOnConnect}
        onReconnect={safeOnReconnect}
        onNodeDragStop={safeOnNodeDragStop}
        onNodeClick={safeOnNodeClick}
        onEdgeClick={safeOnEdgeClick}
        onPaneClick={safeOnPaneClick}
      >
        <Background />
        <Controls />
        {/* Zoom percentage readout, directly above the +/-/fit-view/lock controls — also
            doubles as the easiest way to visually confirm 1b's persistence (reload and
            check it reads the same %).
            Found live (user report): `position="bottom-right"` put this in the exact corner
            the outer panel's own native `resize-y` handle (research.md/008's FR-004) lives
            in, and being a normal DOM element with `pointer-events: auto` sitting on top of
            that corner's pixels was enough to swallow the drag gesture the resize grip
            needs — a real, not just cosmetic, regression. `bottom-left` shares `<Controls>`'s
            own corner (so it stays clear of the resize handle entirely), stacked directly
            above its four buttons via an inline `marginBottom` — a `className` alone loses
            here: React Flow's own `.react-flow__panel.bottom` stylesheet rule (two classes)
            outranks a single Tailwind utility class by CSS specificity regardless of source
            order, confirmed live by the computed margin staying React Flow's own ~15px no
            matter what Tailwind spacing class was tried. `104` is `<Controls>`'s own
            measured height (four 26px buttons) — inline because it has to win outright, not
            because it's expected to ever change. */}
        <Panel
          position="bottom-left"
          className="rounded border border-border bg-background px-1.5 py-0.5 text-4xs text-muted-foreground"
          style={{ marginBottom: 104 + 24 }}
        >
          {/* Divided by `DEFAULT_DIAGRAM_ZOOM` (see its own comment) — reads "100%" at the new
              baseline zoom rather than at React Flow's native 1:1, matching the +/-/fit-view
              controls and persisted zoom below, which still operate on the real, undivided
              value. */}
          {Math.round((currentZoom / DEFAULT_DIAGRAM_ZOOM) * 100)}%
        </Panel>
        {/* 009-ui-fixes-next-iteration follow-up: manual "redraw the diagram" button, above
            the zoom % per the ask — a temporary workaround for the still-not-fully-root-caused
            "diagram goes blank" issue (US3/research.md §3; this session's own
            `diagramSelection` memoization fix found *a* real contributing mechanism, evidently
            not the only one per continued live reports) until that's properly fixed. Refetches
            the Architecture (`onRefresh`, `WorkspacePage.tsx`'s `invalidateArchitecture`) *and*
            forces this whole React Flow instance to remount (`remountNonce`, in `key` above) —
            the same "start over from nothing" a full page reload gives it, matching what the
            user already found actually resolves it, without an actual page reload. */}
        <Panel position="bottom-left" style={{ marginBottom: 104 + 24 + 24 }}>
          <button
            type="button"
            aria-label="Redraw the architecture diagram"
            title="Redraw the architecture diagram"
            className="flex size-4 items-center justify-center rounded border border-border bg-background text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            onClick={() => {
              onRefresh();
              setRemountNonce((n) => n + 1);
            }}
          >
            <RefreshCw className="size-2.5" />
          </button>
        </Panel>
        {/* 011-canvas-connector-popout, spec FR-002: the canvas's own "Add Connector" control
            (formerly here) was removed — connector creation is now consolidated at column 2's
            "Connect" button (`CollectionsPanel.tsx`). */}
        {/* 011-canvas-connector-popout, spec FR-007: opens an enlarged, independent, live-synced
            view of this same canvas (`PopoutCanvasDialog`, `WorkspacePage.tsx`) — see
            `onOpenPopout`'s own doc comment above for why the open/closed state itself lives one
            level up, and why this is omitted (not rendered at all) inside the pop-out's own
            instance of this panel. */}
        {onOpenPopout && (
          <Panel position="top-right">
            <Button
              type="button"
              size="sm"
              variant="outline"
              aria-label="Open the architecture canvas in an enlarged view"
              title="Open the architecture canvas in an enlarged view"
              onClick={onOpenPopout}
            >
              <ArrowUpRight />
            </Button>
          </Panel>
        )}
      </ReactFlow>
      <DiagramResizeHandle
        onDrag={(deltaY) =>
          setDiagramHeight((h) => Math.max(DIAGRAM_MIN_HEIGHT, h + deltaY))
        }
      />
    </div>
  );
}
