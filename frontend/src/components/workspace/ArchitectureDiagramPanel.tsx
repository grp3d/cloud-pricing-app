import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  Handle,
  NodeResizer,
  Position,
  ReactFlow,
  addEdge,
  useOnSelectionChange,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef } from "react";

import { type Collection, type DataConnector } from "../../api/client";
import { useMeasuredHeight } from "../../hooks/useMeasuredHeight";
import { decideNestingChange } from "../../pages/dropTargetDetection";
import {
  type MeasuredLayoutNode,
  childYOffsets,
  computeMeasuredHeight,
} from "../../pages/nodeLayout";
import { summarizeAttributes } from "../../lib/skuDetail";

/** Shared service-list rendering for both node types (004, FR-015). Each listed service is now
 * independently clickable (007-ui-overhaul-shadcn, FR-014) — `stopPropagation` keeps that click
 * from also being interpreted as a click on the containing box (which selects the Collection as
 * a whole, unchanged from 002-006). */
function ServiceList({
  skuSelections,
  onSelectService,
}: {
  skuSelections: Collection["sku_selections"];
  onSelectService: (skuSelectionId: string) => void;
}) {
  if (skuSelections.length === 0) {
    return <p className="mt-1 text-xs text-muted-foreground">No services yet.</p>;
  }
  return (
    <ul className="mt-1 list-none pl-0 text-xs">
      {skuSelections.map((s) => {
        const detail = summarizeAttributes(s.attributes);
        return (
          <li key={s.id}>
            <button
              type="button"
              className="w-full rounded px-1 py-0.5 text-left hover:bg-accent hover:text-accent-foreground"
              onClick={(e) => {
                e.stopPropagation();
                onSelectService(s.id);
              }}
            >
              {s.service_code} / {s.sku}
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

interface ApplicationComponentNodeData {
  [key: string]: unknown;
  label: string;
  skuSelections: Collection["sku_selections"];
  minHeight: number;
  onMeasuredHeight: (height: number) => void;
  onSelectService: (skuSelectionId: string) => void;
  onManualResize: (width: number, height: number) => void;
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
  const { label, skuSelections, minHeight, onMeasuredHeight, onSelectService, onManualResize } =
    data as unknown as ApplicationComponentNodeData;
  const [contentRef, measuredHeight] = useMeasuredHeight<HTMLDivElement>();

  useEffect(() => {
    if (measuredHeight !== null) onMeasuredHeight(measuredHeight + NODE_CHROME_HEIGHT);
  }, [measuredHeight, onMeasuredHeight]);

  return (
    <div className="relative h-full w-full">
      <NodeResizer
        minWidth={160}
        minHeight={minHeight}
        isVisible={selected}
        onResizeEnd={(_, params) => onManualResize(params.width, params.height)}
      />
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
      <div
        className={`box-border h-full w-full overflow-auto rounded bg-card p-2 ${
          selected ? "border-2 border-primary" : "border border-border"
        }`}
      >
        <div ref={contentRef} className="h-auto">
          <strong className="text-xs">{label}</strong>
          <ServiceList skuSelections={skuSelections} onSelectService={onSelectService} />
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
  onMeasuredHeight: (height: number) => void;
  onSelectService: (skuSelectionId: string) => void;
  onManualResize: (width: number, height: number) => void;
}

/** Custom node type for a VPC (002-006). 007 adds the same per-service click targets; 008
 * adds `onManualResize` and moves `<NodeResizer>` out of the scrollable content box — see
 * `ApplicationComponentNode`'s comment above for both (FR-001). */
function VpcNode({ data, selected }: NodeProps) {
  const { label, skuSelections, minHeight, onMeasuredHeight, onSelectService, onManualResize } =
    data as unknown as VpcNodeData;
  const [contentRef, measuredHeight] = useMeasuredHeight<HTMLDivElement>();

  useEffect(() => {
    if (measuredHeight !== null) onMeasuredHeight(measuredHeight + NODE_CHROME_HEIGHT);
  }, [measuredHeight, onMeasuredHeight]);

  return (
    <div className="relative h-full w-full">
      <NodeResizer
        minWidth={220}
        minHeight={minHeight}
        isVisible={selected}
        onResizeEnd={(_, params) => onManualResize(params.width, params.height)}
      />
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
      <div className="box-border h-full w-full overflow-auto rounded border-2 border-primary p-2">
        <div ref={contentRef} className="h-auto">
          <strong className="text-xs">{label}</strong>
          <ServiceList skuSelections={skuSelections} onSelectService={onSelectService} />
        </div>
      </div>
    </div>
  );
}

const nodeTypes = {
  applicationComponent: ApplicationComponentNode,
  vpc: VpcNode,
};

export interface ArchitectureDiagramPanelProps {
  collections: Collection[];
  connectors: DataConnector[];
  ownHeights: Record<string, number>;
  reportHeight: (id: string, height: number) => void;
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
  collections,
  connectors,
  ownHeights,
  reportHeight,
  onSelectedNodeIdsChange,
  onSelectCollection,
  onSelectConnector,
  onSelectService,
  onDeselectAll,
  onCreateConnector,
  onUpdateCollectionParent,
}: ArchitectureDiagramPanelProps) {
  const { getIntersectingNodes } = useReactFlow();

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
  const manualSizeRef = useRef<Map<string, { width: number; height: number }>>(new Map());
  const onManualResize = useCallback((id: string, width: number, height: number) => {
    manualSizeRef.current.set(id, { width, height });
  }, []);

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
      nodes.push({
        id: c.id,
        type: c.type === "vpc" ? "vpc" : "applicationComponent",
        position: { x: (i % 4) * 260, y: Math.floor(i / 4) * 220 },
        data: {
          label: `${c.name} (${c.type})`,
          skuSelections: c.sku_selections,
          minHeight: height,
          onMeasuredHeight: (h: number) => reportHeight(c.id, h),
          onSelectService: (skuSelectionId: string) => onSelectService(skuSelectionId, c.id),
          onManualResize: (w: number, h: number) => onManualResize(c.id, w, h),
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
            label: `${child.name} (${child.type})`,
            skuSelections: child.sku_selections,
            minHeight: childHeight,
            onMeasuredHeight: (h: number) => reportHeight(child.id, h),
            onSelectService: (skuSelectionId: string) =>
              onSelectService(skuSelectionId, child.id),
            onManualResize: (w: number, h: number) => onManualResize(child.id, w, h),
          },
          style: { width: childFinalWidth, height: childFinalHeight },
        });
      });
    });
    return nodes;
  }, [collections, ownHeights, reportHeight, onSelectService, onManualResize]);

  const initialEdges: Edge[] = useMemo(
    () =>
      connectors.map((conn) => ({
        id: conn.id,
        source: conn.from_collection_id,
        target: conn.to_collection_id,
        label: conn.sku_selection ? conn.sku_selection.sku : undefined,
      })),
    [connectors],
  );

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
    if (!dragged || dragged.type !== "application_component") return;

    const intersectingVpcIds = getIntersectingNodes(node)
      .filter((n) => collections.find((c) => c.id === n.id)?.type === "vpc")
      .map((n) => n.id);

    const { changed, newParentId } = decideNestingChange(
      intersectingVpcIds,
      dragged.parent_collection_id ?? null,
    );
    if (changed) {
      onUpdateCollectionParent(dragged.id, newParentId);
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
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        attributionPosition="bottom-left"
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
      </ReactFlow>
    </div>
  );
}
