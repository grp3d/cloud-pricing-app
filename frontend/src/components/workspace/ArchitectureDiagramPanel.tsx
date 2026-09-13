import "@xyflow/react/dist/style.css";

import {
  BaseEdge,
  Background,
  Controls,
  Handle,
  NodeResizeControl,
  Panel,
  Position,
  ReactFlow,
  addEdge,
  getBezierPath,
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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { type Collection, type DataConnector } from "../../api/client";
import { useMeasuredHeight } from "../../hooks/useMeasuredHeight";
import { decideNestingChange } from "../../pages/dropTargetDetection";
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
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";

/** Shared service-list rendering for both node types (004, FR-015). Each listed service is now
 * independently clickable (007-ui-overhaul-shadcn, FR-014) — `stopPropagation` keeps that click
 * from also being interpreted as a click on the containing box (which selects the Collection as
 * a whole, unchanged from 002-006).
 *
 * 009-ui-fixes-next-iteration, US7: `text-4xs` (three steps below 008's `text-xs`, FR-022);
 * each item gets its own border (FR-019); the currently-selected service's name is underlined,
 * exclusively (FR-025, `selectedServiceId` — see `WorkspacePage.tsx`'s `diagramSelection`). */
function ServiceList({
  skuSelections,
  selectedServiceId,
  onSelectService,
}: {
  skuSelections: Collection["sku_selections"];
  selectedServiceId?: string;
  onSelectService: (skuSelectionId: string) => void;
}) {
  if (skuSelections.length === 0) {
    return <p className="mt-1 text-4xs text-muted-foreground">No services yet.</p>;
  }
  return (
    <ul className="mt-1 list-none pl-0 text-4xs">
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
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
      <div
        // 009-ui-fixes-next-iteration, US7, FR-018: darker border shade than 008's
        // `border-border` (verified live against both light and dark theme).
        className={`box-border h-full w-full overflow-auto rounded bg-card p-2 ${
          selected ? "border-2 border-primary" : "border border-gray-400 dark:border-gray-600"
        }`}
      >
        <div ref={contentRef} className="h-auto">
          <strong className={`text-4xs ${isSelected ? "underline" : ""}`}>{label}</strong>
          <ServiceList
            skuSelections={skuSelections}
            selectedServiceId={selectedServiceId}
            onSelectService={onSelectService}
          />
        </div>
      </div>
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
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
      <div
        // 009-ui-fixes-next-iteration, US7, FR-018: darker resting border than 008's
        // `border-primary` alone (which didn't otherwise distinguish selected from
        // unselected); selection still highlights via `border-primary`.
        className={`box-border h-full w-full overflow-auto rounded p-2 ${
          selected ? "border-2 border-primary" : "border-2 border-gray-600 dark:border-gray-400"
        }`}
      >
        <div ref={contentRef} className="h-auto">
          <strong className={`text-4xs ${isSelected ? "underline" : ""}`}>{label}</strong>
          <ServiceList
            skuSelections={skuSelections}
            selectedServiceId={selectedServiceId}
            onSelectService={onSelectService}
          />
        </div>
      </div>
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

/** 009-ui-fixes-next-iteration, US8, FR-026/026a: lets the user create a Connector via two
 * "From Collection"/"To Collection" dropdowns instead of first pre-selecting two Collections
 * on the canvas — the same `onCreateConnector` mutation the existing select-two-and-connect
 * flow already uses (research.md §8), so this is purely a second, more discoverable entry
 * point into it, not a new backend interaction. */
function AddConnectorDialog({
  collections,
  onCreateConnector,
}: {
  collections: Collection[];
  onCreateConnector: (from: string, to: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState<string | undefined>(undefined);
  const [to, setTo] = useState<string | undefined>(undefined);

  // FR-026a: the same Collection can't be chosen in both dropdowns.
  const canConfirm = Boolean(from) && Boolean(to) && from !== to;

  function reset() {
    setFrom(undefined);
    setTo(undefined);
  }

  function handleConfirm() {
    if (!canConfirm || !from || !to) return;
    onCreateConnector(from, to);
    setOpen(false);
    reset();
  }

  return (
    <Panel position="top-right">
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) reset();
        }}
      >
        <Button type="button" size="sm" variant="outline" onClick={() => setOpen(true)}>
          Add Connector
        </Button>
        <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Connector</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium" htmlFor="add-connector-from">
              From Collection
            </label>
            <Select value={from} onValueChange={setFrom}>
              <SelectTrigger id="add-connector-from" className="w-full">
                <SelectValue placeholder="Select a Collection" />
              </SelectTrigger>
              <SelectContent>
                {collections.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium" htmlFor="add-connector-to">
              To Collection
            </label>
            <Select value={to} onValueChange={setTo}>
              <SelectTrigger id="add-connector-to" className="w-full">
                <SelectValue placeholder="Select a Collection" />
              </SelectTrigger>
              <SelectContent>
                {collections.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {from && to && from === to && (
            <p className="text-xs text-destructive">
              From and To must be different Collections.
            </p>
          )}
        </div>
        <DialogFooter>
          <Button type="button" onClick={handleConfirm} disabled={!canConfirm}>
            Add Connector
          </Button>
        </DialogFooter>
      </DialogContent>
      </Dialog>
    </Panel>
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
}: ArchitectureDiagramPanelProps) {
  const { getIntersectingNodes } = useReactFlow();

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
    () => ({ x: 0, y: 0, zoom: readDiagramZoom(architectureId) ?? 1 }),
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

  useOnSelectionChange({
    onChange: ({ nodes: selectedNodes }) =>
      onSelectedNodeIdsChange(selectedNodes.map((n) => n.id)),
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
  const initialEdges: Edge[] = useMemo(() => {
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
      return {
        id: conn.id,
        source: conn.from_collection_id,
        target: conn.to_collection_id,
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
        labelStyle: { fontSize: "var(--text-4xs)", textDecoration: isSelected ? "underline" : "none" },
      };
    });
    const offsets = edgeOffsetIndex(rawEdges);
    return rawEdges.map((edge) => ({
      ...edge,
      type: "offset",
      data: { offsetIndex: offsets[edge.id] ?? 0 },
    }));
  }, [connectors, diagramSelection]);

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

    const { changed, newParentId } = decideNestingChange(
      intersectingVpcIds,
      dragged.parent_collection_id ?? null,
    );
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

  return (
    <div
      // FR-004 (008): raised from the prior 320px default / 320px min-height ceiling (005) —
      // "substantially more of the window's available height" per spec; still fully
      // user-resizable via the native `resize-y` handle, with no artificial max-height
      // capping how much further the user can drag it.
      className="h-full min-h-[600px] resize-y overflow-auto rounded border border-border bg-muted/20"
      style={{ height: 640 }}
    >
      <ReactFlow
        // Keyed by `architectureId` (see the comment above `defaultViewport`) so switching
        // Architectures gets a genuinely fresh pan-zoom instance — `defaultViewport` is only
        // ever read once, at mount, and this component doesn't otherwise remount on its own.
        key={architectureId}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        attributionPosition="bottom-left"
        defaultViewport={defaultViewport}
        onMoveEnd={onMoveEnd}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={safeOnConnect}
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
          {Math.round(currentZoom * 100)}%
        </Panel>
        <AddConnectorDialog collections={collections} onCreateConnector={onCreateConnector} />
      </ReactFlow>
    </div>
  );
}
