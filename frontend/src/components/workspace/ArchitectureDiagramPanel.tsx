import "@xyflow/react/dist/style.css";

import {
  BaseEdge,
  Background,
  ConnectionMode,
  Controls,
  Handle,
  MarkerType,
  NodeResizeControl,
  Panel,
  Position,
  ReactFlow,
  addEdge,
  getBezierPath,
  reconnectEdge,
  useOnSelectionChange,
  useReactFlow,
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
import { ArrowUpRight, RefreshCw } from "lucide-react";

import { type Collection, type DataConnector } from "../../api/client";
import { useMeasuredHeight } from "../../hooks/useMeasuredHeight";
import { decideNestingChange } from "../../pages/dropTargetDetection";
import { updateOrderedSelection } from "../../pages/connectorSelection";
import {
  type MeasuredLayoutNode,
  childYOffsets,
  computeMeasuredHeight,
} from "../../pages/nodeLayout";
import { summarizeAttributes } from "../../lib/skuDetail";
import { edgeOffsetIndex } from "../../lib/edgeOffset";
import { awsDataTransferLabel } from "../../lib/awsDataTransfer";
import {
  readDiagramLayout,
  writeCollectionLayout,
  type CollectionLayoutOverride,
} from "../../lib/diagramLayout";
import { readDiagramZoom, writeDiagramZoom } from "../../lib/diagramViewport";
import {
  ALL_CONNECTOR_SIDES,
  chooseConnectorSides,
  isConnectorSide,
  type ConnectorSide,
  type Rect,
} from "../../lib/connectorRouting";
import { readConnectorSides, writeConnectorSides, type ConnectorSides } from "../../lib/connectorSides";
import { Button } from "../ui/button";

/** Shared service-list rendering for both node types (004, FR-015). Each listed service is now
 * independently clickable (007-ui-overhaul-shadcn, FR-014) — `stopPropagation` keeps that click
 * from also being interpreted as a click on the containing box (which selects the Collection as
 * a whole, unchanged from 002-006).
 *
 * 009-ui-fixes-next-iteration, US7: each item gets its own border (FR-019); the
 * currently-selected service's name is underlined, exclusively (FR-025, `selectedServiceId` —
 * see `WorkspacePage.tsx`'s `diagramSelection`). Text size: `text-4xs` (009) → `text-3xs`
 * (this session's earlier live edit) → `text-2xs` (011-canvas-connector-popout, spec FR-001,
 * one step below 008's `text-xs` floor) — the next increment up the app's own scale. */
function ServiceList({
  skuSelections,
  selectedServiceId,
  onSelectService,
  hideEmptyMessage,
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
}) {
  if (skuSelections.length === 0) {
    return hideEmptyMessage ? null : (
      <p className="mt-1 text-2xs text-muted-foreground">No services yet.</p>
    );
  }
  return (
    <ul className="mt-1 list-none pl-0 text-2xs">
      {skuSelections.map((s) => {
        const detail = summarizeAttributes(s.attributes);
        // 009-ui-fixes-next-iteration, US9, FR-027/028: the derived region-pair label
        // replaces the raw SKU here for AWSDataTransfer Services; every other Service is
        // unaffected (FR-030) since this is `null` for them.
        const dataTransferLabel = awsDataTransferLabel(s.service_code, s.attributes);
        return (
          <li key={s.id}>
            <button
              type="button"
              className={`w-full rounded border border-border px-1 py-0.5 text-left hover:bg-accent hover:text-accent-foreground ${
                s.id === selectedServiceId ? "underline" : ""
              }`}
              onClick={(e) => {
                e.stopPropagation();
                onSelectService(s.id);
              }}
            >
              {s.service_code} / {dataTransferLabel ?? s.sku}
              {detail && <> — {detail}</>}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

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
 * one bad reference. */
function resolveConnectorSides(
  connectors: DataConnector[],
  nodes: Node[],
  persisted: Record<string, ConnectorSides>,
): { resolved: Map<string, ConnectorSides>; newlyComputed: Map<string, ConnectorSides> } {
  const nodesById = new Map(nodes.map((n) => [n.id, n]));
  const usageByCollection = new Map<string, Record<ConnectorSide, number>>();
  const bumpUsage = (collectionId: string, side: ConnectorSide) => {
    const usage = { ...(usageByCollection.get(collectionId) ?? EMPTY_SIDE_USAGE) };
    usage[side] += 1;
    usageByCollection.set(collectionId, usage);
  };

  const resolved = new Map<string, ConnectorSides>();
  const newlyComputed = new Map<string, ConnectorSides>();

  // First pass: every already-persisted Connector claims its sides' usage slots up front, so
  // a same-pass newly-computed Connector correctly sees them as occupied regardless of which
  // order `connectors` happens to list the two groups in.
  for (const conn of connectors) {
    const sides = persisted[conn.id];
    if (!sides) continue;
    resolved.set(conn.id, sides);
    bumpUsage(conn.from_collection_id, sides.from);
    bumpUsage(conn.to_collection_id, sides.to);
  }

  for (const conn of connectors) {
    if (resolved.has(conn.id)) continue;
    const fromRect = absoluteRect(conn.from_collection_id, nodesById);
    const toRect = absoluteRect(conn.to_collection_id, nodesById);
    if (!fromRect || !toRect) continue;
    const { fromSide, toSide } = chooseConnectorSides(
      fromRect,
      toRect,
      usageByCollection.get(conn.from_collection_id) ?? EMPTY_SIDE_USAGE,
      usageByCollection.get(conn.to_collection_id) ?? EMPTY_SIDE_USAGE,
    );
    const sides: ConnectorSides = { from: fromSide, to: toSide };
    resolved.set(conn.id, sides);
    newlyComputed.set(conn.id, sides);
    bumpUsage(conn.from_collection_id, fromSide);
    bumpUsage(conn.to_collection_id, toSide);
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

/** Custom edge renderer for parallel Connectors (009-ui-fixes-next-iteration, US4, FR-010,
 * research.md §4). The first edge in a source/target pair group (`offsetIndex` 0) renders as
 * React Flow's normal bezier path, unchanged. Every subsequent one is displaced perpendicular
 * to the straight line between the two endpoints — this works regardless of node orientation
 * (horizontal, vertical, diagonal), unlike `pathOptions.curvature` (tried first, rejected: for
 * `Position.Left`/`Position.Right` handles on horizontally-aligned nodes — this diagram's most
 * common layout — curvature only extends the control points horizontally, producing an
 * identical-looking path for every offset; confirmed live by inspecting the rendered SVG `d`
 * attributes, which were byte-for-byte identical across differently-curved edges). */
function OffsetEdge({
  id,
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

  if (offsetIndex === 0) {
    const [path, labelX, labelY] = getBezierPath({
      sourceX,
      sourceY,
      sourcePosition,
      targetX,
      targetY,
      targetPosition,
    });
    return (
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
    );
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

  return (
    <BaseEdge
      id={id}
      path={path}
      markerEnd={markerEnd}
      style={style}
      label={label}
      labelStyle={labelStyle}
      labelX={midX}
      labelY={midY}
    />
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
  onRefresh,
  onOpenPopout,
}: ArchitectureDiagramPanelProps) {
  const { getIntersectingNodes } = useReactFlow();

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
  const { zoom: currentZoom } = useViewport();

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
    topLevel.forEach((c, i) => {
      const children = c.type === "vpc" ? (childrenByParent.get(c.id) ?? []) : [];
      const width = c.type === "vpc" ? 220 : 200;
      const layoutNode = toLayoutNode(c);
      const height = computeMeasuredHeight(layoutNode, ownHeights);
      // A manual override's height is clamped to never go *below* the current auto-fit
      // height, so content added after a manual shrink still can't end up clipped again
      // (FR-002 stays satisfied even for a box the user has resized, FR-001's own resize
      // still wins whenever the user has sized it *taller* than auto-fit would).
      const manualSize = manualSizeRef.current.get(c.id);
      const finalWidth = manualSize?.width ?? width;
      const finalHeight = manualSize ? Math.max(manualSize.height, height) : height;
      // 009-ui-fixes-next-iteration, US7, FR-024: a stored position overrides the computed
      // grid slot — only meaningful for top-level Collections (nested children are always
      // auto-stacked within their parent via `childYOffsets` below, unrelated to this).
      // 009-ui-fixes-next-iteration, US7, FR-023: grid spacing increased from 008's 260/220.
      const finalX = manualSize?.x ?? (i % 4) * 300;
      const finalY = manualSize?.y ?? Math.floor(i / 4) * 260;
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
        },
        style: { width: finalWidth, height: finalHeight },
      });
      const offsets = childYOffsets(layoutNode, ownHeights);
      children.forEach((child) => {
        const childLayoutNode = toLayoutNode(child);
        const childHeight = computeMeasuredHeight(childLayoutNode, ownHeights);
        const childManualSize = manualSizeRef.current.get(child.id);
        const childFinalWidth = childManualSize?.width ?? 180;
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
        // value before this).
        markerEnd: { type: MarkerType.ArrowClosed },
      };
    });
    const offsets = edgeOffsetIndex(rawEdges);
    return rawEdges.map((edge) => ({
      ...edge,
      type: "offset",
      data: { offsetIndex: offsets[edge.id] ?? 0 },
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
      className="relative h-full overflow-auto rounded border border-border bg-muted/20"
      style={{ height: diagramHeight }}
    >
      <ReactFlow
        // Keyed by `architectureId` (see the comment above `defaultViewport`) so switching
        // Architectures gets a genuinely fresh pan-zoom instance — `defaultViewport` is only
        // ever read once, at mount, and this component doesn't otherwise remount on its own.
        // `remountNonce` is the same idea, manually triggered by the refresh button.
        key={`${architectureId}-${remountNonce}`}
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
