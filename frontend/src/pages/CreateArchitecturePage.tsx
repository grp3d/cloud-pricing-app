import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  ReactFlow,
  addEdge,
  type Connection,
  type Edge,
  type Node,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { type CatalogSKU, type CollectionType, api } from "../api/client";
import { CatalogSearchPanel } from "../components/CatalogSearchPanel";
import { ConfirmDeleteDialog } from "../components/ConfirmDeleteDialog";
import { DataConnectorPanel } from "../components/DataConnectorPanel";
import { ErrorMessage } from "../components/ErrorMessage";
import { PricingInputsForm, type PricingInputs } from "../components/PricingInputsForm";

function errorMessageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

/**
 * Assemble a single Architecture: Collections as nodes on a React Flow canvas (US2), Data
 * Connectors as edges between them, and — for whichever Collection is selected — the catalog
 * search + pricing inputs to add AWS SKUs to it (US1). Calculate shows the total plus any
 * unpriceable-SKU flags and unconnected-VPCs warning (US1/US3).
 */
export function CreateArchitecturePage() {
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
  const [skuAddError, setSkuAddError] = useState<string | null>(null);

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

  const initialNodes: Node[] = useMemo(
    () =>
      collections.map((c, i) => ({
        id: c.id,
        position: { x: (i % 4) * 200, y: Math.floor(i / 4) * 120 },
        data: { label: `${c.name} (${c.type})` },
        style: c.type === "vpc" ? { border: "2px solid #2563eb" } : undefined,
      })),
    [collections],
  );
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

  async function addSkuToSelectedCollection(inputs: PricingInputs) {
    if (!selectedCollectionId || !pickedSku) return;
    try {
      await api.addSkuSelection(selectedCollectionId, {
        service_code: pickedSku.service_code,
        sku: pickedSku.sku,
        ...inputs,
      });
      setSkuAddError(null);
      setPickedSku(null);
      invalidate();
    } catch (err) {
      setSkuAddError(errorMessageOf(err));
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
                {s.usage_quantity}
              </li>
            ))}
          </ul>

          {skuAddError && (
            <ErrorMessage message={skuAddError} onRetry={() => setSkuAddError(null)} />
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
