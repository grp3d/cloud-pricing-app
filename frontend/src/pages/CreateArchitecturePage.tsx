import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { type CatalogSKU, type Collection, type CollectionType, api } from "../api/client";
import { CatalogSearchPanel } from "../components/CatalogSearchPanel";
import { ConfirmDeleteDialog } from "../components/ConfirmDeleteDialog";
import { DataConnectorPanel } from "../components/DataConnectorPanel";
import { ErrorMessage } from "../components/ErrorMessage";
import { PricingInputsForm, type PricingInputs } from "../components/PricingInputsForm";
import { decideNestingChange } from "./dropTargetDetection";

function errorMessageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

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

  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null);
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(null);
  const [pendingDeleteCollectionId, setPendingDeleteCollectionId] = useState<string | null>(null);
  const [newCollectionType, setNewCollectionType] = useState<CollectionType>("application_component");
  const [newCollectionName, setNewCollectionName] = useState("");
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
    mutationFn: () => api.calculate(architectureId!),
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

    const nodes: Node[] = [];
    topLevel.forEach((c, i) => {
      const children = c.type === "vpc" ? (childrenByParent.get(c.id) ?? []) : [];
      nodes.push({
        id: c.id,
        position: { x: (i % 4) * 260, y: Math.floor(i / 4) * 220 },
        data: { label: `${c.name} (${c.type})` },
        style:
          c.type === "vpc"
            ? {
                border: "2px solid #2563eb",
                width: 220,
                height: Math.max(80, 50 + children.length * 50),
              }
            : undefined,
      });
      // Parent must precede its children in the array — React Flow requirement.
      children.forEach((child, j) => {
        nodes.push({
          id: child.id,
          parentId: c.id,
          position: { x: 20, y: 40 + j * 50 },
          data: { label: `${child.name} (${child.type})` },
        });
      });
    });
    return nodes;
  }, [collections]);
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
        <button onClick={() => calculate.mutate()} disabled={calculate.isPending}>
          Calculate
        </button>
      </section>

      {actionError && (
        <ErrorMessage
          message={actionError}
          onRetry={() => setActionError(null)}
          retryLabel="Dismiss"
        />
      )}

      <div style={{ height: 320, border: "1px solid #ddd", marginTop: 12 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
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
              <PricingInputsForm onSubmit={addSkuToSelectedCollection} />
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
          <p>Priced from snapshot {calculation.snapshot_date}.</p>
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
    </main>
  );
}
