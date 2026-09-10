import { ReactFlowProvider } from "@xyflow/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  type CalculationDuration,
  type CatalogSKU,
  type CollectionType,
  api,
} from "../api/client";
import { ArchitectureDiagramPanel } from "../components/workspace/ArchitectureDiagramPanel";
import { canConnect } from "./connectorSelection";
import { CollectionsPanel, type CollectionsPanelSelection } from "../components/workspace/CollectionsPanel";
import { PricingPanel } from "../components/workspace/PricingPanel";
import { ProviderArchitecturePanel } from "../components/workspace/ProviderArchitecturePanel";
import { ServiceConfigPanel } from "../components/workspace/ServiceConfigPanel";
import { ConfirmDeleteDialog } from "../components/ConfirmDeleteDialog";
import {
  type ServiceConfigSelection,
  existingServiceSelection,
  newServiceSelection,
} from "../lib/serviceConfigSelection";
import type { PricingInputs } from "../components/PricingInputsForm";

function errorMessageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

/**
 * Columns 2, 4, and 5's empty/prompt state before an Architecture is selected, still
 * loading, or not found (FR-011, Edge Cases, quickstart.md Scenario 9). Each of the three
 * panels independently shows this message in its own bordered panel — matching FR-011's
 * "MUST each show a clear empty/prompt state" — rather than one page-wide substitute message
 * (convergence finding, T037): a first-time user should still see the five-panel structure
 * (SC-003) even before picking an Architecture. Column 3 (service configuration) stays
 * genuinely absent, per FR-012/quickstart's "column 3 is simply absent" — there's no service
 * to configure without a Collection to select one from.
 */
function EmptyWorkspacePanels({ message }: { message: string }) {
  const promptTextClassName = "p-4 text-center text-sm text-muted-foreground";
  return (
    <>
      <aside
        className={`flex w-80 shrink-0 items-center justify-center border-r border-border ${promptTextClassName}`}
      >
        {message}
      </aside>
      <div className="min-w-0 flex-1 p-2">
        <div
          className={`flex h-full items-center justify-center rounded border border-border bg-muted/20 ${promptTextClassName}`}
        >
          {message}
        </div>
      </div>
      <aside
        className={`flex w-72 shrink-0 items-center justify-center border-l border-border ${promptTextClassName}`}
      >
        {message}
      </aside>
    </>
  );
}

/**
 * The five-column workspace shell (007-ui-overhaul-shadcn) that replaces the pre-007
 * `LandingPage` + `CreateArchitecturePage` two-page flow. Both `/` and
 * `/architectures/:architectureId` render this same component (research.md §4) — selecting an
 * Architecture in column 1 calls `navigate()` to update the URL without unmounting this shell,
 * so there's no page-reload transition (US1) while Architectures stay individually
 * bookmarkable. This component owns every piece of state and every mutation the five panels
 * collectively need (research.md §5) and passes the relevant slice to each as props — no new
 * state-management library.
 */
export function WorkspacePage() {
  return (
    <ReactFlowProvider>
      <WorkspacePageInner />
    </ReactFlowProvider>
  );
}

function WorkspacePageInner() {
  const { architectureId } = useParams<{ architectureId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // --- Column 1: providers + Architectures ---
  const [selectedProvider, setSelectedProvider] = useState("aws");
  const [newArchitectureName, setNewArchitectureName] = useState("");
  const [pendingDeleteArchitectureId, setPendingDeleteArchitectureId] = useState<string | null>(
    null,
  );

  const providers = useQuery({ queryKey: ["providers"], queryFn: api.listProviders });
  const architectures = useQuery({
    queryKey: ["architectures", selectedProvider],
    queryFn: () => api.listArchitectures(selectedProvider),
  });

  const createArchitecture = useMutation({
    mutationFn: (name: string) => api.createArchitecture(name, selectedProvider),
    onSuccess: (arch) => {
      setNewArchitectureName("");
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["architectures"] });
      navigate(`/architectures/${arch.id}`);
    },
    onError: (err) => setActionError(errorMessageOf(err)),
  });

  const deleteArchitecture = useMutation({
    mutationFn: (id: string) => api.deleteArchitecture(id),
    onSuccess: (_data, id) => {
      setPendingDeleteArchitectureId(null);
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["architectures"] });
      if (architectureId === id) navigate("/");
    },
    onError: (err) => {
      setPendingDeleteArchitectureId(null);
      setActionError(errorMessageOf(err));
    },
  });

  // --- The selected Architecture's data (columns 2-5) ---
  const architecture = useQuery({
    queryKey: ["architecture", architectureId],
    queryFn: () => api.getArchitecture(architectureId!),
    enabled: Boolean(architectureId),
  });
  const collections = useMemo(() => architecture.data?.collections ?? [], [architecture.data]);
  const connectors = useMemo(() => architecture.data?.connectors ?? [], [architecture.data]);
  const invalidateArchitecture = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ["architecture", architectureId] }),
    [queryClient, architectureId],
  );

  // Every SKU Selection across the Architecture, indexed by id, regardless of whether it
  // belongs to a Collection or a Data Connector — lets `ServiceConfigSelection`'s "existing"
  // case stay just an id; this is where it's resolved to the full object (research.md §6).
  const skuSelectionsById = useMemo(() => {
    const map = new Map<string, { selection: (typeof collections)[number]["sku_selections"][number] }>();
    for (const c of collections) {
      for (const s of c.sku_selections) map.set(s.id, { selection: s });
    }
    for (const conn of connectors) {
      if (conn.sku_selection) map.set(conn.sku_selection.id, { selection: conn.sku_selection });
    }
    return map;
  }, [collections, connectors]);

  // --- Selection state shared across columns 2-4 ---
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null);
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(null);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [serviceConfigSelection, setServiceConfigSelection] =
    useState<ServiceConfigSelection>(null);

  const [pendingDeleteCollectionId, setPendingDeleteCollectionId] = useState<string | null>(null);
  const [pendingDeleteConnectorId, setPendingDeleteConnectorId] = useState<string | null>(null);
  const [newCollectionType, setNewCollectionType] = useState<CollectionType>(
    "application_component",
  );
  const [newCollectionName, setNewCollectionName] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [skuActionError, setSkuActionError] = useState<string | null>(null);

  const [ownHeights, setOwnHeights] = useState<Record<string, number>>({});
  const reportHeight = useCallback((id: string, height: number) => {
    setOwnHeights((prev) => (prev[id] === height ? prev : { ...prev, [id]: height }));
  }, []);

  function deselectAll() {
    setSelectedCollectionId(null);
    setSelectedConnectorId(null);
    setServiceConfigSelection(null);
  }

  function selectCollection(id: string) {
    setSelectedCollectionId(id);
    setSelectedConnectorId(null);
    setServiceConfigSelection(null);
  }

  function selectConnector(id: string) {
    setSelectedConnectorId(id);
    setSelectedCollectionId(null);
    const conn = connectors.find((c) => c.id === id);
    setServiceConfigSelection(
      conn?.sku_selection ? existingServiceSelection(conn.sku_selection.id) : null,
    );
  }

  function selectService(skuSelectionId: string, containingCollectionId: string) {
    setSelectedCollectionId(containingCollectionId);
    setSelectedConnectorId(null);
    setServiceConfigSelection(existingServiceSelection(skuSelectionId));
  }

  // --- Collection/Connector mutations ---
  const createCollection = useMutation({
    mutationFn: () => api.createCollection(architectureId!, newCollectionType, newCollectionName),
    onSuccess: () => {
      setNewCollectionName("");
      setActionError(null);
      invalidateArchitecture();
    },
    onError: (err) => setActionError(errorMessageOf(err)),
  });

  const deleteCollection = useMutation({
    mutationFn: (id: string) => api.deleteCollection(id),
    onSuccess: () => {
      setPendingDeleteCollectionId(null);
      if (selectedCollectionId === pendingDeleteCollectionId) deselectAll();
      setActionError(null);
      invalidateArchitecture();
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
      invalidateArchitecture();
    },
    onError: (err) => {
      setActionError(errorMessageOf(err));
      invalidateArchitecture();
    },
  });

  const deleteConnector = useMutation({
    mutationFn: (id: string) => api.deleteConnector(id),
    onSuccess: () => {
      setPendingDeleteConnectorId(null);
      if (selectedConnectorId === pendingDeleteConnectorId) deselectAll();
      setActionError(null);
      invalidateArchitecture();
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
      invalidateArchitecture();
    },
    onError: (err) => {
      setActionError(errorMessageOf(err));
      invalidateArchitecture();
    },
  });

  function handleConnect() {
    if (!canConnect(selectedNodeIds)) return;
    const [from, to] = selectedNodeIds;
    createConnector.mutate({ from, to });
  }

  // --- SKU Selection mutations (column 3) ---
  async function submitNewSku(inputs: PricingInputs) {
    if (serviceConfigSelection?.kind !== "new") return;
    const { catalogSku } = serviceConfigSelection;
    try {
      if (selectedCollectionId) {
        await api.addSkuSelection(selectedCollectionId, {
          service_code: catalogSku.service_code,
          sku: catalogSku.sku,
          ...inputs,
        });
      } else if (selectedConnectorId) {
        await api.attachConnectorSku(selectedConnectorId, {
          service_code: catalogSku.service_code,
          sku: catalogSku.sku,
          ...inputs,
        });
      } else {
        return;
      }
      setSkuActionError(null);
      setServiceConfigSelection(null);
      invalidateArchitecture();
    } catch (err) {
      setSkuActionError(errorMessageOf(err));
    }
  }

  async function submitExistingSku(id: string, inputs: PricingInputs) {
    try {
      await api.updateSkuSelection(id, inputs);
      setSkuActionError(null);
      setServiceConfigSelection(null);
      invalidateArchitecture();
    } catch (err) {
      setSkuActionError(errorMessageOf(err));
    }
  }

  async function removeExistingSku(id: string) {
    try {
      await api.deleteSkuSelection(id);
      setSkuActionError(null);
      if (serviceConfigSelection?.kind === "existing" && serviceConfigSelection.skuSelectionId === id) {
        setServiceConfigSelection(null);
      }
      invalidateArchitecture();
    } catch (err) {
      setSkuActionError(errorMessageOf(err));
    }
  }

  function pickSkuFromSearch(sku: CatalogSKU) {
    setServiceConfigSelection(newServiceSelection(sku));
  }

  // --- Column 5: duration + Calculate ---
  const [calculationDuration, setCalculationDuration] = useState<CalculationDuration>("1_month");
  const [calculation, setCalculation] = useState<Awaited<ReturnType<typeof api.calculate>> | null>(
    null,
  );
  const [calculationError, setCalculationError] = useState<string | null>(null);

  const calculate = useMutation({
    mutationFn: () => api.calculate(architectureId!, calculationDuration),
    onMutate: () => {
      setCalculation(null);
      setCalculationError(null);
    },
    onSuccess: setCalculation,
    onError: (err) => setCalculationError(errorMessageOf(err)),
  });

  // --- Derived view state for the panels ---
  const selectedCollection = collections.find((c) => c.id === selectedCollectionId);
  const selectedConnector = connectors.find((c) => c.id === selectedConnectorId);
  const collectionToDelete = collections.find((c) => c.id === pendingDeleteCollectionId);
  const architectureToDelete = architectures.data?.find(
    (a) => a.id === pendingDeleteArchitectureId,
  );

  const collectionsPanelSelection: CollectionsPanelSelection = selectedCollection
    ? { kind: "collection", id: selectedCollection.id, name: selectedCollection.name }
    : selectedConnector
      ? {
          kind: "connector",
          id: selectedConnector.id,
          attachedSkuSummary: selectedConnector.sku_selection
            ? `${selectedConnector.sku_selection.service_code} / ${selectedConnector.sku_selection.sku}`
            : null,
        }
      : null;

  const resolvedExistingSku =
    serviceConfigSelection?.kind === "existing"
      ? (skuSelectionsById.get(serviceConfigSelection.skuSelectionId)?.selection ?? null)
      : null;

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <ProviderArchitecturePanel
        providers={providers.data ?? []}
        selectedProvider={selectedProvider}
        onSelectProvider={setSelectedProvider}
        architectures={architectures.data ?? []}
        architecturesLoading={architectures.isLoading}
        architecturesError={architectures.isError ? errorMessageOf(architectures.error) : null}
        onRetryArchitectures={() => architectures.refetch()}
        selectedArchitectureId={architectureId}
        onSelectArchitecture={(id) => navigate(`/architectures/${id}`)}
        newArchitectureName={newArchitectureName}
        onNewArchitectureNameChange={setNewArchitectureName}
        onCreateArchitecture={() => createArchitecture.mutate(newArchitectureName.trim())}
        isCreatingArchitecture={createArchitecture.isPending}
        onDeleteArchitecture={setPendingDeleteArchitectureId}
        actionError={actionError}
        onDismissActionError={() => setActionError(null)}
      />

      {!architecture.data && (
        <EmptyWorkspacePanels
          message={
            !architectureId
              ? "Select or create an Architecture to get started."
              : architecture.isLoading
                ? "Loading…"
                : "Architecture not found."
          }
        />
      )}

      {architecture.data && (
        <>
          <CollectionsPanel
            newCollectionType={newCollectionType}
            onNewCollectionTypeChange={setNewCollectionType}
            newCollectionName={newCollectionName}
            onNewCollectionNameChange={setNewCollectionName}
            onAddCollection={() => createCollection.mutate()}
            isAddingCollection={createCollection.isPending}
            canConnect={canConnect(selectedNodeIds)}
            onConnect={handleConnect}
            hasSelectedConnector={Boolean(selectedConnectorId)}
            onRemoveConnector={() =>
              selectedConnectorId && setPendingDeleteConnectorId(selectedConnectorId)
            }
            actionError={actionError}
            onDismissActionError={() => setActionError(null)}
            selection={collectionsPanelSelection}
            onDeleteCollection={setPendingDeleteCollectionId}
            onDeleteConnector={setPendingDeleteConnectorId}
            onPickSku={pickSkuFromSearch}
          />

          <ServiceConfigPanel
            selection={serviceConfigSelection}
            resolvedExisting={resolvedExistingSku}
            onSubmitNew={submitNewSku}
            onSubmitExisting={submitExistingSku}
            onRemoveExisting={removeExistingSku}
            actionError={skuActionError}
            onDismissActionError={() => setSkuActionError(null)}
          />

          <div className="min-w-0 flex-1 p-2">
            <ArchitectureDiagramPanel
              collections={collections}
              connectors={connectors}
              ownHeights={ownHeights}
              reportHeight={reportHeight}
              onSelectedNodeIdsChange={setSelectedNodeIds}
              onSelectCollection={selectCollection}
              onSelectConnector={selectConnector}
              onSelectService={selectService}
              onDeselectAll={deselectAll}
              onCreateConnector={(from, to) => createConnector.mutate({ from, to })}
              onUpdateCollectionParent={(id, parentId) =>
                updateCollectionParent.mutate({ id, parentId })
              }
            />
          </div>

          <PricingPanel
            duration={calculationDuration}
            onDurationChange={setCalculationDuration}
            onCalculate={() => calculate.mutate()}
            isCalculating={calculate.isPending}
            calculation={calculation}
            calculationError={calculationError}
            onRetry={() => calculate.mutate()}
          />
        </>
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

      {architectureToDelete && (
        <ConfirmDeleteDialog
          itemLabel={architectureToDelete.name}
          onCancel={() => setPendingDeleteArchitectureId(null)}
          onConfirm={() => deleteArchitecture.mutate(architectureToDelete.id)}
        />
      )}
    </div>
  );
}
