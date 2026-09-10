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
import { useEffect, useMemo } from "react";

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
}

/** Custom node type for an Application Component (spec FR-007, 005, 006). See prior features'
 * research.md for why height is measured, not estimated, and why Handles are rendered
 * explicitly. 007 adds per-service click targets via `ServiceList`'s `onSelectService`. */
function ApplicationComponentNode({ data, selected }: NodeProps) {
  const { label, skuSelections, minHeight, onMeasuredHeight, onSelectService } =
    data as unknown as ApplicationComponentNodeData;
  const [contentRef, measuredHeight] = useMeasuredHeight<HTMLDivElement>();

  useEffect(() => {
    if (measuredHeight !== null) onMeasuredHeight(measuredHeight + NODE_CHROME_HEIGHT);
  }, [measuredHeight, onMeasuredHeight]);

  return (
    <div
      className={`box-border h-full w-full overflow-auto rounded bg-card p-2 ${
        selected ? "border-2 border-primary" : "border border-border"
      }`}
    >
      <NodeResizer minWidth={160} minHeight={minHeight} isVisible={selected} />
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
      <div ref={contentRef} className="h-auto">
        <strong className="text-sm">{label}</strong>
        <ServiceList skuSelections={skuSelections} onSelectService={onSelectService} />
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
}

/** Custom node type for a VPC (002-006). 007 adds the same per-service click targets. */
function VpcNode({ data, selected }: NodeProps) {
  const { label, skuSelections, minHeight, onMeasuredHeight, onSelectService } =
    data as unknown as VpcNodeData;
  const [contentRef, measuredHeight] = useMeasuredHeight<HTMLDivElement>();

  useEffect(() => {
    if (measuredHeight !== null) onMeasuredHeight(measuredHeight + NODE_CHROME_HEIGHT);
  }, [measuredHeight, onMeasuredHeight]);

  return (
    <div className="box-border h-full w-full overflow-auto rounded border-2 border-primary p-2">
      <NodeResizer minWidth={220} minHeight={minHeight} isVisible={selected} />
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
      <div ref={contentRef} className="h-auto">
        <strong className="text-sm">{label}</strong>
        <ServiceList skuSelections={skuSelections} onSelectService={onSelectService} />
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
        },
        style: { width, height },
      });
      const offsets = childYOffsets(layoutNode, ownHeights);
      children.forEach((child) => {
        const childLayoutNode = toLayoutNode(child);
        const childHeight = computeMeasuredHeight(childLayoutNode, ownHeights);
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
          },
          style: { width: 180, height: childHeight },
        });
      });
    });
    return nodes;
  }, [collections, ownHeights, reportHeight, onSelectService]);

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

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => setNodes(initialNodes), [initialNodes, setNodes]);
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

  return (
    <div
      className="h-full min-h-80 resize-y overflow-auto rounded border border-border bg-muted/20"
      style={{ height: 320 }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        attributionPosition="bottom-left"
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeDragStop={onNodeDragStop}
        onNodeClick={(_, node) => onSelectCollection(node.id)}
        onEdgeClick={(_, edge) => onSelectConnector(edge.id)}
        onPaneClick={onDeselectAll}
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
