import { ReactFlowProvider } from "@xyflow/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  type CalculationDuration,
  type CatalogSKU,
  type CollectionType,
  api,
} from "../api/client";
import { ArchitectureDiagramPanel } from "../components/workspace/ArchitectureDiagramPanel";
import { CollectionsPanel, type CollectionsPanelSelection } from "../components/workspace/CollectionsPanel";
import { ImportArchitectureDialog } from "../components/workspace/ImportArchitectureDialog";
import { PopoutCanvasDialog } from "../components/workspace/PopoutCanvasDialog";
import { PricingPanel } from "../components/workspace/PricingPanel";
import { ProviderArchitecturePanel } from "../components/workspace/ProviderArchitecturePanel";
import { RegionSelectDialog } from "../components/workspace/RegionSelectDialog";
import { ServiceConfigPanel } from "../components/workspace/ServiceConfigPanel";
import { ConfirmDeleteDialog } from "../components/ConfirmDeleteDialog";
import {
  type ServiceConfigSelection,
  existingServiceSelection,
  newServiceSelection,
} from "../lib/serviceConfigSelection";
import type { PricingInputs } from "../components/PricingInputsForm";
import {
  type ColumnId,
  DEFAULT_WIDTHS,
  MIN_WIDTH,
  readColumnWidths,
  writeColumnWidth,
} from "../lib/columnWidths";
import {
  decideBaselineUpdate,
  pricedContentsEqual,
  type PriceChangeSelection,
  type PricedContentsEntry,
} from "../lib/priceChange";
import {
  applyCalculationSuccess,
  readPricingResult,
  removePricingResult,
  shouldAutoCalculate,
  writePricingResult,
  type CalculationRequestVars,
  type PricingResultEntry,
} from "../lib/architecturePricingResults";
import { readPriorCalculation, writePriorCalculation } from "../lib/priorCalculation";

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
  const promptTextClassName = "p-4 text-center text-2xs text-muted-foreground";
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
 * A thin draggable divider between two adjacent columns (US4, FR-012/013, research.md §9):
 * plain pointer-event handlers, no new dependency. `onDrag` receives each pointer-move's
 * delta-x in pixels; the caller decides which column that delta grows or shrinks (a handle
 * left of a column adds the delta to its width, a handle right of one subtracts it).
 */
function ColumnResizeHandle({ onDrag, ariaLabel }: { onDrag: (deltaX: number) => void; ariaLabel: string }) {
  const lastXRef = useRef(0);

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={ariaLabel}
      className="w-1 shrink-0 cursor-col-resize bg-border transition-colors hover:bg-primary/50 active:bg-primary"
      onPointerDown={(e) => {
        e.preventDefault();
        lastXRef.current = e.clientX;
        const target = e.currentTarget;
        target.setPointerCapture(e.pointerId);

        const handleMove = (moveEvent: PointerEvent) => {
          const deltaX = moveEvent.clientX - lastXRef.current;
          lastXRef.current = moveEvent.clientX;
          onDrag(deltaX);
        };
        const handleUp = () => {
          target.removeEventListener("pointermove", handleMove);
          target.removeEventListener("pointerup", handleUp);
        };
        target.addEventListener("pointermove", handleMove);
        target.addEventListener("pointerup", handleUp);
      }}
    />
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

  // --- Column widths (US4, FR-012/013): read once on mount, one localStorage write per
  // resize (T020 — the read/write half of columnWidths.ts). ---
  const [columnWidths, setColumnWidths] = useState<Record<ColumnId, number>>(() => ({
    ...DEFAULT_WIDTHS,
    ...readColumnWidths(),
  }));
  const resizeColumn = useCallback((id: ColumnId, deltaX: number) => {
    setColumnWidths((prev) => {
      const next = Math.max(MIN_WIDTH, prev[id] + deltaX);
      if (next === prev[id]) return prev;
      writeColumnWidth(id, next);
      return { ...prev, [id]: next };
    });
  }, []);

  // --- Column 1: providers + Architectures ---
  const [selectedProvider, setSelectedProvider] = useState("aws");
  const [newArchitectureName, setNewArchitectureName] = useState("");
  const [pendingDeleteArchitectureId, setPendingDeleteArchitectureId] = useState<string | null>(
    null,
  );

  const providers = useQuery({ queryKey: ["providers"], queryFn: api.listProviders });
  // 010-multi-region-support, FR-017: the region-selection prompt only ever offers regions the
  // pricing dataset currently has data for.
  const regions = useQuery({ queryKey: ["regions"], queryFn: api.listRegions });
  const architectures = useQuery({
    queryKey: ["architectures", selectedProvider],
    queryFn: () => api.listArchitectures(selectedProvider),
  });
  // 012-user-accounts-sharing: same query key `TopTabs`'s `IdentityMenu` uses, so this never
  // costs a second network round trip — only whether the sharing/import affordances render
  // (guests never get them, FR-022/FR-027) depends on it here.
  const currentUser = useQuery({ queryKey: ["currentUser"], queryFn: api.getCurrentUser });
  const isGuest = currentUser.data?.username == null;

  const createArchitecture = useMutation({
    mutationFn: (name: string) => api.createArchitecture(name, selectedProvider),
    onSuccess: (arch) => {
      setNewArchitectureName("");
      setArchitectureActionError(null);
      queryClient.invalidateQueries({ queryKey: ["architectures"] });
      navigate(`/architectures/${arch.id}`);
    },
    onError: (err) => setArchitectureActionError(errorMessageOf(err)),
  });

  const deleteArchitecture = useMutation({
    mutationFn: (id: string) => api.deleteArchitecture(id),
    onSuccess: (_data, id) => {
      setPendingDeleteArchitectureId(null);
      setArchitectureActionError(null);
      // 015-canvas-service-icons, spec Edge Cases: a deleted Architecture's stored result goes too.
      removePricingResult(id);
      setResultEntries((prev) => {
        const next = new Map(prev);
        next.delete(id);
        return next;
      });
      setCalculationErrors((prev) => {
        const next = new Map(prev);
        next.delete(id);
        return next;
      });
      queryClient.invalidateQueries({ queryKey: ["architectures"] });
      if (architectureId === id) navigate("/");
    },
    onError: (err) => {
      setPendingDeleteArchitectureId(null);
      setArchitectureActionError(errorMessageOf(err));
    },
  });

  // 012-user-accounts-sharing, spec FR-020: owner-only public/private toggle.
  const toggleArchitecturePublic = useMutation({
    mutationFn: ({ id, isPublic }: { id: string; isPublic: boolean }) =>
      api.setArchitecturePublic(id, isPublic),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["architectures"] }),
    onError: (err) => setArchitectureActionError(errorMessageOf(err)),
  });

  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const importableArchitectures = useQuery({
    queryKey: ["importableArchitectures"],
    queryFn: api.listImportableArchitectures,
    enabled: importDialogOpen,
  });
  const importArchitecture = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => api.importArchitecture(id, name),
    onSuccess: () => {
      setImportDialogOpen(false);
      queryClient.invalidateQueries({ queryKey: ["architectures"] });
    },
    onError: (err) => setArchitectureActionError(errorMessageOf(err)),
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

  // 009-ui-fixes-next-iteration, US9, FR-028: `PricingPanel`'s per-SKU breakdown line only has
  // `CalculationResult.line_items` (service_code/sku/price — no `attributes`, per contracts/
  // api.md §2's "response shape unchanged") to work with, so it can't derive the AWSDataTransfer
  // label itself the way `ArchitectureDiagramPanel`'s `ServiceList` can from its own `Collection`
  // prop. Re-shaped from the `skuSelectionsById` map already built above for exactly this kind
  // of cross-referencing.
  const skuAttributesById = useMemo(() => {
    const map = new Map<string, Record<string, string>>();
    for (const [id, { selection }] of skuSelectionsById) map.set(id, selection.attributes);
    return map;
  }, [skuSelectionsById]);

  // Every SKU Selection's pricing inputs, in `priceChange.ts`'s comparison shape (US5,
  // FR-015/016) — the same flat set `skuSelectionsById` above indexes, just re-shaped and
  // stripped of ids (a Price Change baseline is a value, not a set of live-row references,
  // data-model.md).
  const currentPriceChangeSelections = useMemo<PriceChangeSelection[]>(
    () =>
      Array.from(skuSelectionsById.values(), ({ selection: s }) => ({
        service_code: s.service_code,
        sku: s.sku,
        pricing_term: s.pricing_term,
        purchase_option: s.purchase_option,
        usage_quantity: s.usage_quantity,
      })),
    [skuSelectionsById],
  );

  // 015-canvas-service-icons, FR-018a (data-model.md §4): the same pricing inputs plus the
  // region each is priced in — a Collection's own region, or a Connector's "from" Collection's
  // — compared against a stored result's to flag it as out of date.
  const currentPricedContents = useMemo<PricedContentsEntry[]>(() => {
    const regionByCollectionId = new Map(collections.map((c) => [c.id, c.region]));
    const entries: PricedContentsEntry[] = [];
    const add = (s: (typeof collections)[number]["sku_selections"][number], region?: string) =>
      entries.push({
        service_code: s.service_code,
        sku: s.sku,
        pricing_term: s.pricing_term,
        purchase_option: s.purchase_option,
        usage_quantity: s.usage_quantity,
        region: region ?? null,
      });
    for (const c of collections) for (const s of c.sku_selections) add(s, c.region);
    for (const conn of connectors) {
      if (conn.sku_selection) add(conn.sku_selection, regionByCollectionId.get(conn.from_collection_id));
    }
    return entries;
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
  // 010-multi-region-support, FR-001: shown before creating a new VPC or unattached
  // Application; skipped entirely when nesting an Application into a selected VPC (FR-001a).
  const [regionDialogOpen, setRegionDialogOpen] = useState(false);
  // 016-canvas-icon-layout, FR-012: each column shows only its own errors — architecture
  // actions (column 1) and collection/connector/nesting/move actions (column 2) used to share
  // one message, so every error appeared in both columns.
  const [architectureActionError, setArchitectureActionError] = useState<string | null>(null);
  const [collectionActionError, setCollectionActionError] = useState<string | null>(null);
  const [skuActionError, setSkuActionError] = useState<string | null>(null);

  const [ownHeights, setOwnHeights] = useState<Record<string, number>>({});
  const reportHeight = useCallback((id: string, height: number) => {
    setOwnHeights((prev) => (prev[id] === height ? prev : { ...prev, [id]: height }));
  }, []);

  // 011-canvas-connector-popout, spec FR-007: whether the enlarged pop-out canvas view is
  // open — owned here since column 4's own trigger button and `PopoutCanvasDialog` (rendered
  // as siblings below) both need it. `PopoutCanvasDialog` owns everything else about its own
  // canvas instance (selection, box heights, size) locally — only this boolean is lifted.
  const [popoutOpen, setPopoutOpen] = useState(false);

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
  // 010-multi-region-support, FR-001/FR-001a: `region` is supplied from the RegionSelectDialog;
  // `parentCollectionId` is supplied instead when nesting an Application into a selected VPC
  // (region is then inherited server-side, never sent).
  const createCollection = useMutation({
    mutationFn: (vars: { region?: string; parentCollectionId?: string }) =>
      api.createCollection(
        architectureId!,
        newCollectionType,
        newCollectionName,
        vars.region,
        vars.parentCollectionId,
      ),
    onSuccess: () => {
      setNewCollectionName("");
      setCollectionActionError(null);
      setRegionDialogOpen(false);
      invalidateArchitecture();
    },
    onError: (err) => setCollectionActionError(errorMessageOf(err)),
  });

  /** 010-multi-region-support, FR-001/FR-001a: adding an Application while a VPC is selected
   * skips the region prompt and nests directly (region inherited server-side); every other
   * "+Add" click opens the region-selection dialog instead. */
  function handleAddCollectionClick() {
    if (newCollectionType === "application_component" && selectedCollection?.type === "vpc") {
      createCollection.mutate({ parentCollectionId: selectedCollection.id });
    } else {
      setRegionDialogOpen(true);
    }
  }

  // 016-canvas-icon-layout, FR-004a: dragging a service's icon into another box (same region)
  // moves the service there; a failure shows in column 2 and the canvas puts the icon back.
  const moveService = useMutation({
    mutationFn: (vars: { id: string; collectionId: string }) =>
      api.updateSkuSelection(vars.id, { collection_id: vars.collectionId }),
    onSuccess: () => {
      setCollectionActionError(null);
      invalidateArchitecture();
    },
    onError: (err) => setCollectionActionError(errorMessageOf(err)),
  });
  const onMoveService = useCallback(
    async (id: string, collectionId: string) => {
      await moveService.mutateAsync({ id, collectionId });
    },
    [moveService],
  );

  const deleteCollection = useMutation({
    mutationFn: (id: string) => api.deleteCollection(id),
    onSuccess: () => {
      setPendingDeleteCollectionId(null);
      if (selectedCollectionId === pendingDeleteCollectionId) deselectAll();
      setCollectionActionError(null);
      invalidateArchitecture();
    },
    onError: (err) => {
      setPendingDeleteCollectionId(null);
      setCollectionActionError(errorMessageOf(err));
    },
  });

  const createConnector = useMutation({
    mutationFn: ({ from, to }: { from: string; to: string }) =>
      api.createConnector(architectureId!, from, to),
    onSuccess: () => {
      setCollectionActionError(null);
      invalidateArchitecture();
    },
    onError: (err) => {
      setCollectionActionError(errorMessageOf(err));
      invalidateArchitecture();
    },
  });

  const deleteConnector = useMutation({
    mutationFn: (id: string) => api.deleteConnector(id),
    onSuccess: () => {
      setPendingDeleteConnectorId(null);
      if (selectedConnectorId === pendingDeleteConnectorId) deselectAll();
      setCollectionActionError(null);
      invalidateArchitecture();
    },
    onError: (err) => {
      setPendingDeleteConnectorId(null);
      setCollectionActionError(errorMessageOf(err));
    },
  });

  const updateCollectionParent = useMutation({
    mutationFn: ({ id, parentId }: { id: string; parentId: string | null }) =>
      api.updateCollectionParent(id, parentId),
    onSuccess: () => {
      setCollectionActionError(null);
      invalidateArchitecture();
    },
    onError: (err) => {
      setCollectionActionError(errorMessageOf(err));
      invalidateArchitecture();
    },
  });

  const updateCollectionRegion = useMutation({
    mutationFn: ({ id, region }: { id: string; region: string }) =>
      api.updateCollectionRegion(id, region),
    onSuccess: () => {
      setCollectionActionError(null);
      invalidateArchitecture();
    },
    onError: (err) => setCollectionActionError(errorMessageOf(err)),
  });

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

  // 015-canvas-service-icons, US4 (FR-015-FR-022, research.md §6): column 5 shows the *active*
  // Architecture's own last result, never whichever calculation happened to run last. Results
  // are kept per Architecture (in memory here, persisted per browser by
  // `architecturePricingResults.ts` so they survive a reload); errors and in-flight requests are
  // per Architecture too, in memory only. Each calculation carries everything it needs as
  // mutation variables captured at request time, so one that finishes after the user has
  // switched Architectures is still recorded against the one it was for (FR-020) — and the
  // Price Change baseline logic (US5 of 008, `priceChange.ts`) runs against *that*
  // Architecture's baseline and contents, never the currently-displayed one's.
  const [resultEntries, setResultEntries] = useState<ReadonlyMap<string, PricingResultEntry>>(
    () => new Map(),
  );
  const resultEntriesRef = useRef(resultEntries);
  resultEntriesRef.current = resultEntries;
  const [calculationErrors, setCalculationErrors] = useState<ReadonlyMap<string, string>>(
    () => new Map(),
  );
  // The ref is the synchronous source of truth (so a re-render before TanStack's async
  // `onMutate` can't double-fire an automatic calculation); the state mirrors it for rendering.
  const inFlightRef = useRef(new Set<string>());
  const [inFlight, setInFlight] = useState<ReadonlySet<string>>(() => new Set());
  const markInFlight = useCallback((id: string, pending: boolean) => {
    if (pending) inFlightRef.current.add(id);
    else inFlightRef.current.delete(id);
    setInFlight(new Set(inFlightRef.current));
  }, []);

  const storedEntry = useMemo(
    () => (architectureId ? readPricingResult(architectureId) : null),
    [architectureId],
  );
  const activeEntry = architectureId
    ? (resultEntries.get(architectureId) ?? storedEntry ?? undefined)
    : undefined;
  const architectureLoaded = Boolean(architectureId) && architecture.data?.id === architectureId;

  const calculate = useMutation({
    mutationFn: (vars: CalculationRequestVars) =>
      api.calculate(vars.architectureId, vars.duration),
    onMutate: (vars) => {
      setCalculationErrors((prev) => {
        const next = new Map(prev);
        next.delete(vars.architectureId);
        return next;
      });
    },
    onSuccess: async (result, vars) => {
      const decision = decideBaselineUpdate({
        prior: vars.prior,
        currentSelections: vars.priceChangeSelections,
        newDuration: vars.duration,
      });
      // "direct": compare directly against the stored baseline's own total. "duration_
      // adjusted" (content AND Duration both changed, FR-016a) and "duration_only" (Duration
      // alone changed, 009 FR-002/003) both need the comparison total repriced from the
      // *prior* selections at the *new* Duration through the real calculation, never a
      // scaled estimate.
      const comparisonTotal =
        decision === "direct"
          ? vars.prior!.total
          : decision === "duration_adjusted" || decision === "duration_only"
            ? (await api.calculateSnapshot(vars.duration, vars.prior!.selections)).total_price
            : null;
      const { entry, newBaseline } = applyCalculationSuccess({
        entries: resultEntriesRef.current,
        vars,
        result,
        decision,
        comparisonTotal,
        previousEntry:
          resultEntriesRef.current.get(vars.architectureId) ??
          readPricingResult(vars.architectureId) ??
          undefined,
        now: new Date().toISOString(),
      });
      writePricingResult(vars.architectureId, entry);
      if (newBaseline) writePriorCalculation(vars.architectureId, newBaseline);
      setResultEntries((prev) => new Map(prev).set(vars.architectureId, entry));
    },
    onError: (err, vars) =>
      setCalculationErrors((prev) =>
        new Map(prev).set(vars.architectureId, errorMessageOf(err)),
      ),
    onSettled: (_data, _err, vars) => markInFlight(vars.architectureId, false),
  });

  const { mutate: mutateCalculation } = calculate;

  /** Start a calculation of the *active* Architecture at `duration`, capturing its contents and
   * Price Change baseline now (FR-020). Used by Calculate, Retry, and the automatic first
   * calculation alike, so all three follow the same baseline rules (FR-022). */
  const startCalculation = useCallback(
    (duration: CalculationDuration) => {
      if (!architectureId) return;
      markInFlight(architectureId, true);
      mutateCalculation({
        architectureId,
        duration,
        pricedContents: currentPricedContents,
        priceChangeSelections: currentPriceChangeSelections,
        prior: readPriorCalculation(architectureId),
      });
    },
    [
      architectureId,
      mutateCalculation,
      currentPricedContents,
      currentPriceChangeSelections,
      markInFlight,
    ],
  );

  // FR-018b: switching to an Architecture with a stored result shows the Duration that result
  // was calculated at; one without keeps the current Duration (and is auto-calculated at it).
  useEffect(() => {
    if (!architectureId) return;
    const entry = resultEntriesRef.current.get(architectureId) ?? readPricingResult(architectureId);
    if (entry) setCalculationDuration(entry.duration);
  }, [architectureId]);

  // FR-017: calculate automatically the first time an Architecture with services but no stored
  // result becomes active — once its own data has loaded, so the captured contents are its own.
  useEffect(() => {
    if (!architectureLoaded) return;
    if (
      shouldAutoCalculate({
        architectureId,
        hasSelections: skuSelectionsById.size > 0,
        hasStoredEntry: activeEntry !== undefined,
        isInFlight: Boolean(architectureId && inFlightRef.current.has(architectureId)),
        hasError: Boolean(architectureId && calculationErrors.has(architectureId)),
      })
    ) {
      startCalculation(calculationDuration);
    }
  }, [
    architectureLoaded,
    architectureId,
    skuSelectionsById,
    activeEntry,
    calculationErrors,
    startCalculation,
    calculationDuration,
  ]);

  const isActiveCalculating = Boolean(architectureId && inFlight.has(architectureId));
  // FR-018a: the stored result no longer matches what the Architecture would price today.
  const isOutOfDate =
    architectureLoaded &&
    activeEntry !== undefined &&
    !pricedContentsEqual(activeEntry.pricedContents, currentPricedContents);

  // --- Derived view state for the panels ---
  const selectedCollection = collections.find((c) => c.id === selectedCollectionId);
  const selectedConnector = connectors.find((c) => c.id === selectedConnectorId);
  const collectionToDelete = collections.find((c) => c.id === pendingDeleteCollectionId);
  const architectureToDelete = architectures.data?.find(
    (a) => a.id === pendingDeleteArchitectureId,
  );

  // 010-multi-region-support, spec FR-003: a collection is locked once it has a service, or,
  // for a VPC, a nested Application — mirrors the server-side `is_collection_locked` check.
  const selectedCollectionLocked = selectedCollection
    ? selectedCollection.sku_selections.length > 0 ||
      (selectedCollection.type === "vpc" &&
        collections.some((c) => c.parent_collection_id === selectedCollection.id))
    : false;

  const collectionsPanelSelection: CollectionsPanelSelection = selectedCollection
    ? {
        kind: "collection",
        id: selectedCollection.id,
        name: selectedCollection.name,
        region: selectedCollection.region,
        locked: selectedCollectionLocked,
      }
    : selectedConnector
      ? {
          kind: "connector",
          id: selectedConnector.id,
          attachedSkuSummary: selectedConnector.sku_selection
            ? `${selectedConnector.sku_selection.service_code} / ${selectedConnector.sku_selection.sku}`
            : null,
        }
      : null;

  // 010-multi-region-support, spec FR-005/FR-006: service search is scoped to the selected
  // collection's region, or, for a selected connector, its "from" collection's region.
  const searchRegion = selectedCollection
    ? selectedCollection.region
    : selectedConnector
      ? collections.find((c) => c.id === selectedConnector.from_collection_id)?.region
      : undefined;

  const resolvedExistingSku =
    serviceConfigSelection?.kind === "existing"
      ? (skuSelectionsById.get(serviceConfigSelection.skuSelectionId)?.selection ?? null)
      : null;

  // 009-ui-fixes-next-iteration, US7, FR-025: precisely which ONE diagram object (Collection,
  // Connector, or Service) is currently selected, for underlining its name — deliberately NOT
  // just `selectedCollectionId`/`selectedConnectorId` directly, since `selectService` also sets
  // `selectedCollectionId` to the service's *containing* Collection (so column 3 stays showing
  // that Collection's context); underlining that container too would violate FR-025's "no
  // unselected object's name" rule. An in-progress "new" service (not yet an existing
  // SKUSelection) has no diagram object of its own to underline.
  //
  // Found live (009 follow-up, via user report): this MUST be `useMemo`-stable, not a plain
  // `const` recomputed fresh on every render. `ArchitectureDiagramPanel`'s `initialNodes`/
  // `initialEdges` both depend on it, and a `useEffect` there re-applies `initialNodes` into
  // React Flow's own node state on every one of *their* recomputes — an unmemoized object
  // literal here made that fire on literally every `WorkspacePage` render (typing in a search
  // field, an unrelated query refetch, anything), clobbering React Flow's own in-progress
  // node-dimension measurement far more often than real selection changes warrant. Confirmed
  // live: attaching a Service to a Connector between two content-less Collections left both
  // Collection boxes permanently `visibility: hidden` (React Flow's own DOM, `0` for
  // `.react-flow__edge` count too) — this is plausibly the actual mechanism behind US3/
  // research.md §3's "diagram goes blank" reports that 9 combined targeted attempts (008 +
  // this feature's own T001/T008) could never reproduce: it needs enough re-render churn in
  // a narrow enough window, which this object literal was manufacturing on nearly every
  // render regardless of cause.
  const diagramSelection = useMemo<
    { kind: "collection" | "connector" | "service"; id: string } | null
  >(
    () =>
      serviceConfigSelection?.kind === "existing"
        ? { kind: "service", id: serviceConfigSelection.skuSelectionId }
        : selectedConnectorId
          ? { kind: "connector", id: selectedConnectorId }
          : selectedCollectionId
            ? { kind: "collection", id: selectedCollectionId }
            : null,
    [serviceConfigSelection, selectedConnectorId, selectedCollectionId],
  );

  return (
    <div className="flex h-full w-full overflow-hidden">
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
        actionError={architectureActionError}
        onDismissActionError={() => setArchitectureActionError(null)}
        width={columnWidths.provider}
        isGuest={isGuest}
        onToggleArchitecturePublic={(id, isPublic) =>
          toggleArchitecturePublic.mutate({ id, isPublic })
        }
        onOpenImportDialog={() => setImportDialogOpen(true)}
      />

      <ImportArchitectureDialog
        open={importDialogOpen}
        onOpenChange={setImportDialogOpen}
        data={importableArchitectures.data}
        onConfirm={(id, name) => importArchitecture.mutate({ id, name })}
        isSubmitting={importArchitecture.isPending}
      />

      <ColumnResizeHandle
        ariaLabel="Resize provider/Architecture panel"
        onDrag={(dx) => resizeColumn("provider", dx)}
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
            onAddCollection={handleAddCollectionClick}
            isAddingCollection={createCollection.isPending}
            collections={collections}
            selectedNodeIds={selectedNodeIds}
            onCreateConnector={(from, to) => createConnector.mutate({ from, to })}
            hasSelectedConnector={Boolean(selectedConnectorId)}
            onRemoveConnector={() =>
              selectedConnectorId && setPendingDeleteConnectorId(selectedConnectorId)
            }
            actionError={collectionActionError}
            onDismissActionError={() => setCollectionActionError(null)}
            selection={collectionsPanelSelection}
            onDeleteCollection={setPendingDeleteCollectionId}
            onDeleteConnector={setPendingDeleteConnectorId}
            onPickSku={pickSkuFromSearch}
            searchRegion={searchRegion}
            regions={regions.data?.regions ?? []}
            onUpdateCollectionRegion={(id, region) =>
              updateCollectionRegion.mutate({ id, region })
            }
            isUpdatingCollectionRegion={updateCollectionRegion.isPending}
            width={columnWidths.collections}
          />

          <ColumnResizeHandle
            ariaLabel="Resize Architecture Editor panel"
            onDrag={(dx) => resizeColumn("collections", dx)}
          />

          <ServiceConfigPanel
            selection={serviceConfigSelection}
            resolvedExisting={resolvedExistingSku}
            onSubmitNew={submitNewSku}
            onSubmitExisting={submitExistingSku}
            onRemoveExisting={removeExistingSku}
            actionError={skuActionError}
            onDismissActionError={() => setSkuActionError(null)}
            width={columnWidths.service}
          />

          <ColumnResizeHandle
            ariaLabel="Resize Service Editor panel"
            onDrag={(dx) => resizeColumn("service", dx)}
          />

          <div className="min-w-0 flex-1 p-2">
            <ArchitectureDiagramPanel
              architectureId={architectureId!}
              collections={collections}
              connectors={connectors}
              ownHeights={ownHeights}
              reportHeight={reportHeight}
              diagramSelection={diagramSelection}
              onSelectedNodeIdsChange={setSelectedNodeIds}
              onSelectCollection={selectCollection}
              onSelectConnector={selectConnector}
              onSelectService={selectService}
              onDeselectAll={deselectAll}
              onCreateConnector={(from, to) => createConnector.mutate({ from, to })}
              onUpdateCollectionParent={(id, parentId) =>
                updateCollectionParent.mutate({ id, parentId })
              }
              onRejectedNesting={(applicationName, vpcName) =>
                setCollectionActionError(
                  `"${applicationName}" is in a different region than "${vpcName}" — an ` +
                    "Application can only nest inside a VPC in the same region.",
                )
              }
              onRefresh={invalidateArchitecture}
              onOpenPopout={() => setPopoutOpen(true)}
              onMoveService={onMoveService}
              onMoveRejected={setCollectionActionError}
            />
          </div>

          <ColumnResizeHandle
            ariaLabel="Resize pricing panel"
            onDrag={(dx) => resizeColumn("pricing", -dx)}
          />

          <PricingPanel
            duration={calculationDuration}
            onDurationChange={setCalculationDuration}
            onCalculate={() => startCalculation(calculationDuration)}
            isCalculating={isActiveCalculating}
            // As before 015, a result isn't shown while its own recalculation is running.
            calculation={isActiveCalculating ? null : (activeEntry?.result ?? null)}
            calculationError={(architectureId && calculationErrors.get(architectureId)) || null}
            onRetry={() => startCalculation(calculationDuration)}
            width={columnWidths.pricing}
            priceChange={activeEntry?.priceChange ?? null}
            skuAttributesById={skuAttributesById}
            isOutOfDate={isOutOfDate && !isActiveCalculating}
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

      <RegionSelectDialog
        open={regionDialogOpen}
        onOpenChange={setRegionDialogOpen}
        regions={regions.data?.regions ?? []}
        onConfirm={(region) => createCollection.mutate({ region })}
        isSubmitting={createCollection.isPending}
      />

      {architecture.data && (
        <PopoutCanvasDialog
          open={popoutOpen}
          onOpenChange={setPopoutOpen}
          architectureId={architectureId!}
          collections={collections}
          connectors={connectors}
          onCreateConnector={(from, to) => createConnector.mutate({ from, to })}
          onUpdateCollectionParent={(id, parentId) =>
            updateCollectionParent.mutate({ id, parentId })
          }
          onRejectedNesting={(applicationName, vpcName) =>
            setCollectionActionError(
              `"${applicationName}" is in a different region than "${vpcName}" — an ` +
                "Application can only nest inside a VPC in the same region.",
            )
          }
          onRefresh={invalidateArchitecture}
          onMoveService={onMoveService}
          onMoveRejected={setCollectionActionError}
          diagramSelection={diagramSelection}
          onSelectedNodeIdsChange={setSelectedNodeIds}
          onSelectCollection={selectCollection}
          onSelectConnector={selectConnector}
          onSelectService={selectService}
          onDeselectAll={deselectAll}
        />
      )}
    </div>
  );
}
