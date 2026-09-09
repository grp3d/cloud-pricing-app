import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  Handle,
  NodeResizer,
  Position,
  ReactFlow,
  ReactFlowProvider,
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
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import {
  type CalculationDuration,
  type CatalogSKU,
  type Collection,
  type CollectionType,
  api,
} from "../api/client";
import { CatalogSearchPanel } from "../components/CatalogSearchPanel";
import { ConfirmDeleteDialog } from "../components/ConfirmDeleteDialog";
import { DataConnectorPanel } from "../components/DataConnectorPanel";
import { ErrorMessage } from "../components/ErrorMessage";
import { PricingInputsForm, type PricingInputs } from "../components/PricingInputsForm";
import { SkuDetail } from "../components/SkuDetail";
import { useMeasuredHeight } from "../hooks/useMeasuredHeight";
import { summarizeAttributes } from "../lib/skuDetail";
import { canConnect } from "./connectorSelection";
import { decideNestingChange } from "./dropTargetDetection";
import { type MeasuredLayoutNode, childYOffsets, computeMeasuredHeight } from "./nodeLayout";

function errorMessageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

/** Shared service-list rendering for both node types (004, FR-015: a VPC shows its own
 * directly-attached services "the same way an Application Component shows its own contained
 * services"). */
function ServiceList({ skuSelections }: { skuSelections: Collection["sku_selections"] }) {
  if (skuSelections.length === 0) {
    return <p style={{ margin: "4px 0 0", fontSize: 12, color: "#9ca3af" }}>No services yet.</p>;
  }
  return (
    <ul style={{ margin: "4px 0 0", paddingLeft: 16, fontSize: 12 }}>
      {skuSelections.map((s) => {
        const detail = summarizeAttributes(s.attributes);
        return (
          <li key={s.id}>
            {s.service_code} / {s.sku}
            {detail && <> — {detail}</>}
          </li>
        );
      })}
    </ul>
  );
}

/** The outer node box's own vertical chrome — its top+bottom `padding: 8` plus the thicker of
 * its two possible border widths (`2px` selected / `1px` unselected, so this stays a safe
 * over-estimate rather than needing to react to selection changes) — that sits *outside* the
 * content div `useMeasuredHeight` measures (its `contentRect` excludes padding/border). Without
 * adding this back, a node's total height would be set to exactly its content's height, leaving
 * no room for the padding/border around that content and clipping the last couple of pixels of
 * text (found via live verification: `outerDiv.scrollHeight` exceeded `offsetHeight` by exactly
 * the padding amount before this constant was added). A couple of px of slack when unselected is
 * a fine tradeoff against ever under-measuring (spec FR-003's "always... without any of it being
 * clipped"). */
const NODE_CHROME_HEIGHT = 2 * 8 + 2 * 2; // padding top+bottom, plus worst-case (selected) border

interface ApplicationComponentNodeData {
  [key: string]: unknown;
  label: string;
  skuSelections: Collection["sku_selections"];
  minHeight: number;
  /** Reports this node's real rendered "own content" height up to the canvas so it can recompute
   * layout from a measurement instead of an estimate (005-resizable-canvas-boxes, FR-003/FR-004). */
  onMeasuredHeight: (height: number) => void;
}

/** Custom node type for an Application Component (spec FR-007): shows its name plus the
 * services it contains — or an empty state. Its own-content block (label + `ServiceList`) is
 * `height: "auto"` and measured live via `useMeasuredHeight`, reported up through
 * `onMeasuredHeight` — the canvas then sizes this node from that real measurement, not a
 * character-count estimate, so long wrapped detail text is never clipped (005,
 * research.md #2). Also carries a `NodeResizer` for manual *width* resize (004, spec FR-010,
 * FR-011); a manual resize is superseded the next time the canvas recomputes from fresh content
 * (research.md #5, now driven by measured rather than estimated heights), so it needs no
 * persistence of its own. */
function ApplicationComponentNode({ data, selected }: NodeProps) {
  const { label, skuSelections, minHeight, onMeasuredHeight } =
    data as unknown as ApplicationComponentNodeData;
  const [contentRef, measuredHeight] = useMeasuredHeight<HTMLDivElement>();

  useEffect(() => {
    if (measuredHeight !== null) onMeasuredHeight(measuredHeight + NODE_CHROME_HEIGHT);
  }, [measuredHeight, onMeasuredHeight]);

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        boxSizing: "border-box",
        border: selected ? "2px solid #2563eb" : "1px solid #9ca3af",
        borderRadius: 4,
        background: "#fff",
        padding: 8,
        overflow: "auto",
      }}
    >
      <NodeResizer minWidth={160} minHeight={minHeight} isVisible={selected} />
      {/* React Flow's default node type renders these automatically; a custom node type must
          render them itself — their absence here was the actual cause of "can't draw
          connectors" (004, FR-011, research.md #8). */}
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
      <div ref={contentRef} style={{ height: "auto" }}>
        <strong>{label}</strong>
        <ServiceList skuSelections={skuSelections} />
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
}

/** Custom node type for a VPC: same header styling as before (002-vpc-component-nesting), also
 * showing its own directly-attached services (004, FR-015). Its own-content block is measured
 * the same way `ApplicationComponentNode`'s is (005) — nested child boxes are separate sibling
 * nodes (`parentId`), not DOM descendants of this div, so this measures exactly the VPC's own
 * header/content area, which is precisely what the stacking algorithm needs as an input (see
 * `nodeLayout.ts`'s module doc and research.md #2). `NodeResizer`'s `minHeight` is that same
 * real-or-estimated content-required size — the library's own resize-constraint mechanism
 * enforces spec FR-011's "a VPC never shrinks below what its nested children need" directly, now
 * cascading through however many levels of nesting exist (004, FR-016/FR-017; 005, FR-005), with
 * no custom validation code (research.md #5, #6). */
function VpcNode({ data, selected }: NodeProps) {
  const { label, skuSelections, minHeight, onMeasuredHeight } = data as unknown as VpcNodeData;
  const [contentRef, measuredHeight] = useMeasuredHeight<HTMLDivElement>();

  useEffect(() => {
    if (measuredHeight !== null) onMeasuredHeight(measuredHeight + NODE_CHROME_HEIGHT);
  }, [measuredHeight, onMeasuredHeight]);

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        boxSizing: "border-box",
        border: "2px solid #2563eb",
        borderRadius: 4,
        padding: 8,
        overflow: "auto",
      }}
    >
      <NodeResizer minWidth={220} minHeight={minHeight} isVisible={selected} />
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
      <div ref={contentRef} style={{ height: "auto" }}>
        <strong>{label}</strong>
        <ServiceList skuSelections={skuSelections} />
      </div>
    </div>
  );
}

const nodeTypes = {
  applicationComponent: ApplicationComponentNode,
  vpc: VpcNode,
};

/**
 * Assemble a single Architecture: Collections as nodes on a React Flow canvas (US2), Data
 * Connectors as edges between them, and — for whichever Collection is selected — the catalog
 * search + pricing inputs to add AWS SKUs to it (US1). Calculate shows the total plus any
 * unpriceable-SKU flags and unconnected-VPCs warning (US1/US3). Application Components can be
 * dragged into a VPC to nest them (002-vpc-component-nesting, US1).
 */
export function CreateArchitecturePage() {
  // useReactFlow() (used below to detect drop targets) only works inside a ReactFlowProvider,
  // which must be an ancestor of the component calling it — hence this thin wrapper.
  return (
    <ReactFlowProvider>
      <CreateArchitecturePageInner />
    </ReactFlowProvider>
  );
}

function CreateArchitecturePageInner() {
  const { architectureId } = useParams<{ architectureId: string }>();
  const queryClient = useQueryClient();

  const architecture = useQuery({
    queryKey: ["architecture", architectureId],
    queryFn: () => api.getArchitecture(architectureId!),
    enabled: Boolean(architectureId),
  });

  // Real, browser-measured "own content" height per node id (005-resizable-canvas-boxes,
  // FR-003/FR-004) — populated live by each node's `useMeasuredHeight`, via `reportHeight`
  // below. Absent entries (e.g. a node's very first render) fall back to the character-count
  // estimate inside `computeMeasuredHeight`/`childYOffsets` (research.md #2).
  const [ownHeights, setOwnHeights] = useState<Record<string, number>>({});
  const reportHeight = useCallback((id: string, height: number) => {
    // Bail out (return the same object) when nothing actually changed, so a node re-reporting
    // the same height after a parent re-render doesn't retrigger the layout recompute below —
    // otherwise `initialNodes`' `ownHeights` dependency would never settle.
    setOwnHeights((prev) => (prev[id] === height ? prev : { ...prev, [id]: height }));
  }, []);

  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null);
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(null);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [pendingDeleteCollectionId, setPendingDeleteCollectionId] = useState<string | null>(null);
  const [pendingDeleteConnectorId, setPendingDeleteConnectorId] = useState<string | null>(null);
  const [newCollectionType, setNewCollectionType] = useState<CollectionType>("application_component");
  const [newCollectionName, setNewCollectionName] = useState("");
  const [calculationDuration, setCalculationDuration] = useState<CalculationDuration>("1_month");
  const [calculation, setCalculation] = useState<
    Awaited<ReturnType<typeof api.calculate>> | null
  >(null);
  const [calculationError, setCalculationError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pickedSku, setPickedSku] = useState<CatalogSKU | null>(null);
  const [skuActionError, setSkuActionError] = useState<string | null>(null);
  const [editingSkuSelectionId, setEditingSkuSelectionId] = useState<string | null>(null);

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["architecture", architectureId] });

  const createCollection = useMutation({
    mutationFn: () => api.createCollection(architectureId!, newCollectionType, newCollectionName),
    onSuccess: () => {
      setNewCollectionName("");
      setActionError(null);
      invalidate();
    },
    onError: (err) => setActionError(errorMessageOf(err)),
  });

  const deleteCollection = useMutation({
    mutationFn: (id: string) => api.deleteCollection(id),
    onSuccess: () => {
      setPendingDeleteCollectionId(null);
      if (selectedCollectionId === pendingDeleteCollectionId) setSelectedCollectionId(null);
      setActionError(null);
      invalidate();
    },
    onError: (err) => {
      setPendingDeleteCollectionId(null);
      setActionError(errorMessageOf(err));
    },
  });

  const createConnector = useMutation({
    mutationFn: ({ from, to }: { from: string; to: string }) =>
      api.createConnector(architectureId!, from, to),
    onSuccess: () => {
      setActionError(null);
      invalidate();
    },
    onError: (err) => {
      setActionError(errorMessageOf(err));
      // The edge was drawn optimistically in onConnect before this rejection; resync the
      // canvas from the server's actual state so a failed connector never stays visible.
      invalidate();
    },
  });

  const deleteConnector = useMutation({
    mutationFn: (id: string) => api.deleteConnector(id),
    onSuccess: () => {
      setPendingDeleteConnectorId(null);
      if (selectedConnectorId === pendingDeleteConnectorId) setSelectedConnectorId(null);
      setActionError(null);
      invalidate();
    },
    onError: (err) => {
      setPendingDeleteConnectorId(null);
      setActionError(errorMessageOf(err));
    },
  });

  const updateCollectionParent = useMutation({
    mutationFn: ({ id, parentId }: { id: string; parentId: string | null }) =>
      api.updateCollectionParent(id, parentId),
    onSuccess: () => {
      setActionError(null);
      invalidate();
    },
    onError: (err) => {
      setActionError(errorMessageOf(err));
      // The node may have visually moved during the drag before this rejection; resync the
      // canvas from the server's actual state, same pattern as a rejected connector.
      invalidate();
    },
  });

  const calculate = useMutation({
    mutationFn: () => api.calculate(architectureId!, calculationDuration),
    // Clear any prior result up front so a failed recalculation never leaves a stale total
    // on screen looking like a fresh answer (Constitution Principle I).
    onMutate: () => {
      setCalculation(null);
      setCalculationError(null);
    },
    onSuccess: setCalculation,
    onError: (err) => setCalculationError(errorMessageOf(err)),
  });

  // --- React Flow: Collections as nodes, Data Connectors as edges ---
  const collections = useMemo(() => architecture.data?.collections ?? [], [architecture.data]);
  const connectors = useMemo(() => architecture.data?.connectors ?? [], [architecture.data]);

  const { getIntersectingNodes } = useReactFlow();

  // Tracks React Flow's own multi-select state (shift/ctrl+click) — drives the "Connect"
  // action's enabled state (004-canvas-pricing-improvements, FR-008/FR-009, research.md #7).
  // Independent of `selectedCollectionId`/`onNodeClick` below, which only opens the details
  // panel for the most recently clicked node.
  useOnSelectionChange({
    onChange: ({ nodes: selectedNodes }) => setSelectedNodeIds(selectedNodes.map((n) => n.id)),
  });

  function handleConnect() {
    if (!canConnect(selectedNodeIds)) return;
    const [from, to] = selectedNodeIds;
    createConnector.mutate({ from, to });
  }

  // Application Components nested inside a VPC (parent_collection_id set) render as child
  // nodes of that VPC's node (002-vpc-component-nesting, spec FR-001-003). No `extent:
  // 'parent'` constraint is set — a user must be able to drag a nested node fully outside its
  // VPC's bounds to un-nest it (FR-003); clamping movement to the parent would make that
  // impossible. Positions are recomputed from Collection order on every refetch rather than
  // preserved from free-form dragging — consistent with how top-level nodes already behaved
  // before this feature.
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

    // Recurses through however many levels of nesting a Collection's subtree has (004,
    // FR-016/FR-017) — today's data model only ever produces one level (spec Assumptions), but
    // the height math itself makes no such assumption (research.md #6).
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
        },
        style: { width, height },
      });
      // Parent must precede its children in the array — React Flow requirement. Nested
      // children start below the VPC's own (real-measured-or-estimated) content — its header
      // plus its own directly-attached services, FR-015 — rather than a fixed offset, so they
      // never visually overlap it (005: this offset is now real when a measurement exists).
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
          },
          style: { width: 180, height: childHeight },
        });
      });
    });
    return nodes;
  }, [collections, ownHeights, reportHeight]);
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
    createConnector.mutate({ from: connection.source, to: connection.target });
    setEdges((eds) => addEdge(connection, eds));
  }

  const onNodeDragStop = (_event: MouseEvent | TouchEvent, node: Node) => {
    const dragged = collections.find((c) => c.id === node.id);
    // Only an Application Component can be nested (spec FR-004) — dragging a VPC is a no-op
    // for nesting purposes.
    if (!dragged || dragged.type !== "application_component") return;

    const intersectingVpcIds = getIntersectingNodes(node)
      .filter((n) => collections.find((c) => c.id === n.id)?.type === "vpc")
      .map((n) => n.id);

    const { changed, newParentId } = decideNestingChange(
      intersectingVpcIds,
      dragged.parent_collection_id ?? null,
    );
    if (changed) {
      updateCollectionParent.mutate({ id: dragged.id, parentId: newParentId });
    }
  };

  async function addSkuToSelectedCollection(inputs: PricingInputs) {
    if (!selectedCollectionId || !pickedSku) return;
    try {
      await api.addSkuSelection(selectedCollectionId, {
        service_code: pickedSku.service_code,
        sku: pickedSku.sku,
        ...inputs,
      });
      setSkuActionError(null);
      setPickedSku(null);
      invalidate();
    } catch (err) {
      setSkuActionError(errorMessageOf(err));
    }
  }

  async function updateSkuSelection(id: string, inputs: PricingInputs) {
    try {
      await api.updateSkuSelection(id, inputs);
      setSkuActionError(null);
      setEditingSkuSelectionId(null);
      invalidate();
    } catch (err) {
      setSkuActionError(errorMessageOf(err));
    }
  }

  async function removeSkuSelection(id: string) {
    try {
      await api.deleteSkuSelection(id);
      setSkuActionError(null);
      if (editingSkuSelectionId === id) setEditingSkuSelectionId(null);
      invalidate();
    } catch (err) {
      setSkuActionError(errorMessageOf(err));
    }
  }

  const selectedCollection = collections.find((c) => c.id === selectedCollectionId);
  const selectedConnector = connectors.find((c) => c.id === selectedConnectorId);
  const collectionToDelete = collections.find((c) => c.id === pendingDeleteCollectionId);

  if (architecture.isLoading) return <p>Loading…</p>;
  if (!architecture.data) return <p>Architecture not found.</p>;

  return (
    <main style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h1>{architecture.data.name}</h1>

      <section style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <select
          value={newCollectionType}
          onChange={(e) => setNewCollectionType(e.target.value as CollectionType)}
        >
          <option value="application_component">Application Component</option>
          <option value="vpc">VPC</option>
        </select>
        <input
          placeholder="Collection name"
          value={newCollectionName}
          onChange={(e) => setNewCollectionName(e.target.value)}
        />
        <button
          disabled={!newCollectionName.trim()}
          onClick={() => createCollection.mutate()}
        >
          Add Collection
        </button>
        <label>
          Duration{" "}
          <select
            value={calculationDuration}
            onChange={(e) => setCalculationDuration(e.target.value as CalculationDuration)}
          >
            <option value="1_day">1 day</option>
            <option value="1_month">1 month</option>
            <option value="1_year">1 year</option>
          </select>
        </label>
        <button onClick={() => calculate.mutate()} disabled={calculate.isPending}>
          Calculate
        </button>
        <button
          onClick={handleConnect}
          disabled={!canConnect(selectedNodeIds)}
          title="Select exactly two boxes on the canvas to connect them"
        >
          Connect
        </button>
        <button
          onClick={() => selectedConnectorId && setPendingDeleteConnectorId(selectedConnectorId)}
          disabled={!selectedConnectorId}
          title="Select a connector on the canvas to remove it"
        >
          Remove Connector
        </button>
      </section>

      {actionError && (
        <ErrorMessage
          message={actionError}
          onRetry={() => setActionError(null)}
          retryLabel="Dismiss"
        />
      )}

      {/* Native browser resize (005-resizable-canvas-boxes, FR-001/FR-002): the page is a
          single-column, full-width layout with nothing beside the canvas, so "resize" only
          meaningfully means height — `resize: vertical` gives a single-drag-gesture resize with
          no custom drag-handle code (research.md #1). `minHeight` matches today's default so the
          canvas can never be dragged below a usable size (spec Edge Cases); it resets to that
          default on reload since it's just the element's own computed style, satisfying the
          spec's non-persistence Assumption. */}
      <div
        style={{
          height: 320,
          minHeight: 320,
          resize: "vertical",
          overflow: "auto",
          border: "1px solid #ddd",
          marginTop: 12,
        }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          // React Flow's default "React Flow" attribution badge sits bottom-right, exactly on
          // top of the wrapper's native `resize: vertical` grip (also bottom-right) — live
          // verification found it was intercepting the drag before it could reach the browser's
          // resize corner at all, silently defeating FR-001. Moving it clear of that corner is
          // all FR-001 needs; the attribution itself is unaffected (still shown, still credits
          // React Flow).
          attributionPosition="bottom-left"
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeDragStop={onNodeDragStop}
          onNodeClick={(_, node) => {
            setSelectedCollectionId(node.id);
            setSelectedConnectorId(null);
          }}
          onEdgeClick={(_, edge) => {
            setSelectedConnectorId(edge.id);
            setSelectedCollectionId(null);
          }}
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>

      {selectedCollection && (
        <section style={{ marginTop: 12, border: "1px solid #eee", padding: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <h3>{selectedCollection.name}</h3>
            <button onClick={() => setPendingDeleteCollectionId(selectedCollection.id)}>
              Delete Collection
            </button>
          </div>
          <ul>
            {selectedCollection.sku_selections.map((s) => (
              <li key={s.id}>
                {s.service_code} / {s.sku} — {s.pricing_term}, {s.purchase_option}, qty{" "}
                {s.usage_quantity}{" "}
                <button onClick={() => setEditingSkuSelectionId(s.id)}>Edit</button>{" "}
                <button onClick={() => removeSkuSelection(s.id)}>Remove</button>
                {editingSkuSelectionId === s.id && (
                  <PricingInputsForm
                    submitLabel="Save"
                    initial={{
                      pricing_term: s.pricing_term,
                      purchase_option: s.purchase_option,
                      usage_quantity: s.usage_quantity,
                    }}
                    unit={s.unit}
                    onSubmit={(inputs) => updateSkuSelection(s.id, inputs)}
                  />
                )}
              </li>
            ))}
          </ul>

          {skuActionError && (
            <ErrorMessage message={skuActionError} onRetry={() => setSkuActionError(null)} />
          )}
          {pickedSku ? (
            <>
              <p>
                Selected: {pickedSku.service_name} — {pickedSku.summary}
              </p>
              <SkuDetail attributes={pickedSku.attributes} />
              <PricingInputsForm onSubmit={addSkuToSelectedCollection} unit={pickedSku.unit} />
            </>
          ) : (
            <CatalogSearchPanel onAdd={setPickedSku} />
          )}
        </section>
      )}

      {selectedConnector && (
        <DataConnectorPanel
          connector={selectedConnector}
          onChanged={invalidate}
          onClose={() => setSelectedConnectorId(null)}
        />
      )}

      {calculationError && (
        <ErrorMessage
          message={calculationError}
          onRetry={() => calculate.mutate()}
        />
      )}

      {calculation && (
        <section aria-label="Calculation result" style={{ marginTop: 12 }}>
          <h3>Total: {calculation.total_price} {calculation.currency}</h3>
          <p>
            For {calculation.duration.replace("_", " ")}, priced from snapshot{" "}
            {calculation.snapshot_date}.
          </p>
          {calculation.warnings.map((w) => (
            <p key={w.code} role="alert" style={{ color: "#b45309" }}>
              ⚠ {w.message}
            </p>
          ))}
          {calculation.unpriceable.length > 0 && (
            <div role="alert" style={{ color: "#b91c1c" }}>
              <p>Some SKUs could not be priced and are excluded from the total:</p>
              <ul>
                {calculation.unpriceable.map((u) => (
                  <li key={u.sku_selection_id}>
                    {u.service_code} / {u.sku} — {u.reason}
                    {u.components.length > 0 && <> (in {u.components.join(", ")})</>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {collectionToDelete && (
        <ConfirmDeleteDialog
          itemLabel={collectionToDelete.name}
          onCancel={() => setPendingDeleteCollectionId(null)}
          onConfirm={() => deleteCollection.mutate(collectionToDelete.id)}
        />
      )}

      {pendingDeleteConnectorId && (
        <ConfirmDeleteDialog
          itemLabel="this Data Connector"
          onCancel={() => setPendingDeleteConnectorId(null)}
          onConfirm={() => deleteConnector.mutate(pendingDeleteConnectorId)}
        />
      )}
    </main>
  );
}
