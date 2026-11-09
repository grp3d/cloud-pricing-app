import { ReactFlowProvider } from "@xyflow/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, useCallback } from "react";
import { useParams } from "react-router-dom";

import {
  type ArchitectureDetail,
  type CalculationDuration,
  type CatalogSKU,
  type CollectionType,
  type DataConnector,
  type ProviderCode,
  api,
} from "../api/client";
import { PROVIDER_LABELS, asProviderCode } from "../lib/providerPricing";
import { Tooltip, TooltipContent, TooltipTrigger } from "../components/ui/tooltip";
import { ArchitectureDiagramPanel } from "../components/workspace/ArchitectureDiagramPanel";
import {
  CollectionsPanel,
  type CollectionsPanelSelection,
} from "../components/workspace/CollectionsPanel";
import { PopoutCanvasDialog } from "../components/workspace/PopoutCanvasDialog";
import { InspectorPanel } from "../components/workspace/InspectorPanel";
import { PricingPanel } from "../components/workspace/PricingPanel";
import { RegionSelectDialog } from "../components/workspace/RegionSelectDialog";
import { ServiceConfigPanel } from "../components/workspace/ServiceConfigPanel";
import { ConfirmDeleteDialog } from "../components/ConfirmDeleteDialog";
import {
  type ServiceConfigSelection,
  existingServiceSelection,
} from "../lib/serviceConfigSelection";
import type { PricingInputs } from "../components/PricingInputsForm";
import { defaultPricingInputs } from "../lib/pricingInputs";
import { type ServiceLabel, serviceLabel } from "../lib/serviceLabel";
import {
  type ColumnId,
  DEFAULT_WIDTHS,
  MIN_WIDTH,
  readColumnWidths,
  useColumnWidths,
  writeColumnWidth,
} from "../lib/columnWidths";
import {
  readColumnCollapsed,
  useColumnCollapsed,
  writeColumnCollapsed,
} from "../lib/columnCollapse";
import { fitZones } from "../lib/fitZones";
import {
  type InspectorAction,
  nextArrangement,
  readInspector,
  writeInspector,
} from "../lib/inspectorLayout";
import { preferencesStore, usePreferences } from "../lib/preferences";
import {
  decideBaselineUpdate,
  pricedContentsEqual,
  type PriceChangeSelection,
  type PricedContentsEntry,
} from "../lib/priceChange";
import {
  applyCalculationSuccess,
  readPricingResult,
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
 * The three zones' empty/prompt state before an Architecture is selected, still
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
        className={`flex w-[360px] shrink-0 items-center justify-center border-l border-border ${promptTextClassName}`}
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
function ColumnResizeHandle({
  onDrag,
  ariaLabel,
}: {
  onDrag: (deltaX: number) => void;
  ariaLabel: string;
}) {
  const lastXRef = useRef(0);

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={ariaLabel}
      // 021 (FR-006, FR-027): reachable by keyboard too — the arrow keys resize in 16px steps.
      tabIndex={0}
      className="focus-ring w-1 shrink-0 cursor-col-resize bg-border transition-colors hover:bg-primary/50 focus-visible:bg-primary active:bg-primary"
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
          e.preventDefault();
          onDrag(e.key === "ArrowLeft" ? -16 : 16);
        }
      }}
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
 * The workspace shell (007-ui-overhaul-shadcn) that replaces the pre-007
 * `LandingPage` + `CreateArchitecturePage` two-page flow. 021: three zones under the header —
 * the Architecture Editor sidebar, the canvas, and the inspector (Pricing and Service tabs);
 * the architecture list moved to the header's menu. Both `/` and
 * `/architectures/:architectureId` render this same component (research.md §4) — selecting an
 * Architecture in the header menu calls `navigate()` to update the URL without unmounting this shell,
 * so there's no page-reload transition (US1) while Architectures stay individually
 * bookmarkable. This component owns every piece of state and every mutation the five panels
 * collectively need (research.md §5) and passes the relevant slice to each as props — no new
 * state-management library.
 */
/** 021 US5 (FR-037): shown when a search result's arrow has nowhere to add the service. */
export const NO_ADD_TARGET = "Select a box or connector on the canvas first";

export function WorkspacePage() {
  return (
    <ReactFlowProvider>
      <WorkspacePageInner />
    </ReactFlowProvider>
  );
}

function WorkspacePageInner() {
  const { architectureId } = useParams<{ architectureId: string }>();
  const queryClient = useQueryClient();

  // --- Column widths (US4, FR-012/013): saved to the user's account since 019 (FR-023), each
  // resize applied at once and saved in the background (columnWidths.ts). ---
  const storedWidths = useColumnWidths();
  const columnWidths: Record<ColumnId, number> = { ...DEFAULT_WIDTHS, ...storedWidths };
  const resizeColumn = useCallback((id: ColumnId, deltaX: number) => {
    const current = readColumnWidths()[id] ?? DEFAULT_WIDTHS[id];
    const next = Math.max(MIN_WIDTH, current + deltaX);
    if (next !== current) writeColumnWidth(id, next);
  }, []);
  // 021 (FR-010): the sidebar and the inspector each collapse to a rail.
  const collapsedColumns = useColumnCollapsed();
  const inspectorCollapsed = collapsedColumns.inspector ?? false;
  // 021 (research R4): rendered widths for the window; fitting never writes preferences.
  // The row changes size only with the window, so it is measured on mount, on window resize
  // and by a ResizeObserver — not after every render, which this page does very often.
  const rowRef = useRef<HTMLDivElement>(null);
  const [rowWidth, setRowWidth] = useState<number | null>(null);
  useLayoutEffect(() => {
    const el = rowRef.current;
    if (!el) return;
    const measure = () => {
      const next = el.getBoundingClientRect().width;
      setRowWidth((prev) => (prev === next ? prev : next));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);
  const RESIZE_HANDLES_PX = 8;
  const fitted = fitZones(
    rowWidth === null ? Number.POSITIVE_INFINITY : rowWidth - RESIZE_HANDLES_PX,
    {
      sidebar: columnWidths.collections,
      sidebarCollapsed: collapsedColumns.collections ?? false,
      inspector: columnWidths.inspector,
      inspectorCollapsed,
    },
  );

  // --- The inspector's arrangement (021, research R5/R7): merged or split, which tab is in
  // front. Every change goes through `nextArrangement` and is saved to the account. ---
  const dispatchInspector = useCallback((action: InspectorAction) => {
    const current = readInspector(preferencesStore.current.workspace);
    const next = nextArrangement(current, action);
    if (next !== current) writeInspector(next);
  }, []);
  // FR-018a: a calculation that finishes while the inspector is collapsed marks its rail.
  const [newResult, setNewResult] = useState(false);
  const setInspectorCollapsed = useCallback((collapsed: boolean) => {
    writeColumnCollapsed("inspector", collapsed);
    if (!collapsed) setNewResult(false);
  }, []);
  /** FR-015, FR-018a: selecting a service (or picking a SKU to add) brings Service forward,
   * expanding a collapsed inspector. */
  const serviceSelected = useCallback(() => {
    dispatchInspector({ type: "service-selected" });
    if (readColumnCollapsed().inspector) setInspectorCollapsed(false);
  }, [dispatchInspector, setInspectorCollapsed]);

  // --- The workspace provider (021, research R3) ---
  // Column 1's provider picker is gone: the provider follows the open architecture. With none
  // open, it is the last provider used (019, FR-023), if still active, else AWS.
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.listProviders });
  const [prefs, patchSection, prefsLoaded] = usePreferences();
  const inspectorArrangement = readInspector(prefs.workspace);
  const storedProvider = prefs.workspace?.last_provider ?? null;
  const storedActive =
    storedProvider !== null &&
    (!providers.data || providers.data.some((p) => p.code === storedProvider && p.active));
  const fallbackProvider = storedActive ? storedProvider : "aws";
  useEffect(() => {
    if (prefsLoaded && providers.isSuccess && storedProvider !== null && !storedActive) {
      patchSection("workspace", { ...prefs.workspace, last_provider: null });
    }
  }, [
    prefsLoaded,
    providers.isSuccess,
    storedProvider,
    storedActive,
    prefs.workspace,
    patchSection,
  ]);

  // --- The selected Architecture's data (columns 2-5) ---
  const architecture = useQuery({
    queryKey: ["architecture", architectureId],
    queryFn: () => api.getArchitecture(architectureId!),
    enabled: Boolean(architectureId),
  });
  const collections = useMemo(() => architecture.data?.collections ?? [], [architecture.data]);
  const connectors = useMemo(() => architecture.data?.connectors ?? [], [architecture.data]);
  // 019 (FR-002, FR-006): the open architecture's provider picks the regions, catalog and
  // editor fields (021, FR-004); with none open, the fallback above does.
  const pricingProvider: ProviderCode = asProviderCode(
    architecture.data?.provider ?? fallbackProvider,
  );
  const canvasTitle = architecture.data
    ? `${PROVIDER_LABELS[pricingProvider]} · ${architecture.data.name}`
    : "";
  // 021 (research R3): opening (or creating) an architecture saves its provider as the last
  // one used, as picking it in Column 1 did. Only an active provider is saved: the clean-up
  // above clears an inactive one, and the two would otherwise undo each other forever.
  const openedProvider = architecture.data?.provider;
  const openedActive = Boolean(
    openedProvider && providers.data?.some((p) => p.code === openedProvider && p.active),
  );
  useEffect(() => {
    if (prefsLoaded && openedActive && openedProvider && openedProvider !== storedProvider) {
      patchSection("workspace", {
        ...prefs.workspace,
        last_provider: asProviderCode(openedProvider),
      });
    }
  }, [prefsLoaded, openedActive, openedProvider, storedProvider, prefs.workspace, patchSection]);
  // 010-multi-region-support, FR-017: the region-selection prompt only ever offers regions the
  // pricing dataset currently has data for — 019: the provider's own regions.
  const regions = useQuery({
    queryKey: ["regions", pricingProvider],
    queryFn: () => api.listRegions(pricingProvider),
  });
  const invalidateArchitecture = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ["architecture", architectureId] }),
    [queryClient, architectureId],
  );

  // Every SKU Selection across the Architecture, indexed by id, regardless of whether it
  // belongs to a Collection or a Data Connector — lets `ServiceConfigSelection`'s "existing"
  // case stay just an id; this is where it's resolved to the full object (research.md §6).
  const skuSelectionsById = useMemo(() => {
    const map = new Map<
      string,
      { selection: (typeof collections)[number]["sku_selections"][number] }
    >();
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

  // 021 US7 (FR-047): readable names for the Price per Sku list, from the same map.
  const skuLabelsById = useMemo(() => {
    const map = new Map<string, ServiceLabel>();
    for (const [id, { selection }] of skuSelectionsById) map.set(id, serviceLabel(selection));
    return map;
  }, [skuSelectionsById]);

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
        // 020 (research R1): GCP vCPUs/memory and Azure OS change the price too.
        provider_options: s.provider_options ?? null,
      });
    for (const c of collections) for (const s of c.sku_selections) add(s, c.region);
    for (const conn of connectors) {
      if (conn.sku_selection)
        add(conn.sku_selection, regionByCollectionId.get(conn.from_collection_id));
    }
    return entries;
  }, [collections, connectors]);

  // Every SKU Selection's pricing inputs, in `priceChange.ts`'s comparison shape (US5,
  // FR-015/016) — a Price Change baseline is a value, not a set of live-row references
  // (data-model.md). 020 (data-model §3): the same entries as above, so a version 2 baseline
  // carries each selection's region and options and the Duration-switch re-pricing can use them.
  const currentPriceChangeSelections: PriceChangeSelection[] = currentPricedContents;

  // --- Selection state shared across columns 2-4 ---
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null);
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(null);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [serviceConfigSelection, setServiceConfigSelection] =
    useState<ServiceConfigSelection>(null);

  const [pendingDeleteCollectionId, setPendingDeleteCollectionId] = useState<string | null>(null);
  const [pendingDeleteConnectorId, setPendingDeleteConnectorId] = useState<string | null>(null);
  const [newCollectionType, setNewCollectionType] =
    useState<CollectionType>("application_component");
  const [newCollectionName, setNewCollectionName] = useState("");
  // 010-multi-region-support, FR-001: shown before creating a new VPC or unattached
  // Application; skipped entirely when nesting an Application into a selected VPC (FR-001a).
  const [regionDialogOpen, setRegionDialogOpen] = useState(false);
  // 016-canvas-icon-layout, FR-012: each zone shows only its own errors (architecture actions
  // now show in the header menu, 021).
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
    if (conn?.sku_selection) serviceSelected();
  }

  function selectService(skuSelectionId: string, containingCollectionId: string) {
    setSelectedCollectionId(containingCollectionId);
    setSelectedConnectorId(null);
    setServiceConfigSelection(existingServiceSelection(skuSelectionId));
    serviceSelected();
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

  // 019 (FR-026, FR-028): arrow style and direction, applied to the cached architecture at
  // once so the diagram redraws without waiting; a failure restores it from the server.
  const updateConnectorArrow = useMutation({
    mutationFn: ({
      id,
      change,
    }: {
      id: string;
      change: { arrow_style?: DataConnector["arrow_style"]; arrow_reversed?: boolean };
    }) => api.updateConnector(id, change),
    onMutate: ({ id, change }) => {
      queryClient.setQueryData<ArchitectureDetail>(["architecture", architectureId], (old) =>
        old
          ? {
              ...old,
              connectors: old.connectors.map((c) => (c.id === id ? { ...c, ...change } : c)),
            }
          : old,
      );
    },
    onSuccess: () => setCollectionActionError(null),
    onError: (err) => setCollectionActionError(errorMessageOf(err)),
    onSettled: () => invalidateArchitecture(),
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
      // 021 US5 (FR-038): the saved service stays selected and open in the Service tab.
      invalidateArchitecture();
      return true;
    } catch (err) {
      setSkuActionError(errorMessageOf(err));
      return false;
    }
  }

  async function removeExistingSku(id: string) {
    try {
      await api.deleteSkuSelection(id);
      setSkuActionError(null);
      if (
        serviceConfigSelection?.kind === "existing" &&
        serviceConfigSelection.skuSelectionId === id
      ) {
        setServiceConfigSelection(null);
      }
      invalidateArchitecture();
    } catch (err) {
      setSkuActionError(errorMessageOf(err));
    }
  }

  // 021 US5 (FR-037): a search result's arrow adds the service straight away, with the values
  // the Service form starts with, to the selected box or connector, then opens it in the
  // Service tab, where it can be adjusted and saved.
  const [searchNotice, setSearchNotice] = useState<string | null>(null);
  useEffect(() => setSearchNotice(null), [selectedCollectionId, selectedConnectorId]);
  async function pickSkuFromSearch(sku: CatalogSKU) {
    const collectionId = selectedCollectionId;
    const connectorId = collectionId ? null : selectedConnectorId;
    if (!collectionId && !connectorId) {
      setSearchNotice(NO_ADD_TARGET);
      return;
    }
    const body = {
      service_code: sku.service_code,
      sku: sku.sku,
      ...defaultPricingInputs({
        provider: pricingProvider,
        priceTypes: sku.price_types,
        kind: sku.kind,
        attributes: sku.attributes,
      }),
    };
    try {
      const created = collectionId
        ? await api.addSkuSelection(collectionId, body)
        : await api.attachConnectorSku(connectorId!, body);
      setSearchNotice(null);
      setSkuActionError(null);
      // Wait for the refetch, so the Service tab can show the new service at once.
      await invalidateArchitecture();
      setServiceConfigSelection(existingServiceSelection(created.id));
      serviceSelected();
    } catch (err) {
      setSearchNotice(errorMessageOf(err));
    }
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
  const architectureIdRef = useRef(architectureId);
  architectureIdRef.current = architectureId;

  const calculate = useMutation({
    mutationFn: (vars: CalculationRequestVars) => api.calculate(vars.architectureId, vars.duration),
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
        provider: vars.provider,
      });
      // "direct": compare directly against the stored baseline's own total. "duration_
      // adjusted" (content AND Duration both changed, FR-016a) and "duration_only" (Duration
      // alone changed, 009 FR-002/003) both need the comparison total repriced from the
      // *prior* selections at the *new* Duration through the real calculation, never a
      // scaled estimate. 020 (research R2): the re-pricing carries the provider and each prior
      // selection's region and options. "unavailable" (a legacy GCP/Azure baseline, FR-005)
      // makes no snapshot call at all.
      const comparisonTotal =
        decision === "direct"
          ? vars.prior!.total
          : decision === "duration_adjusted" || decision === "duration_only"
            ? (await api.calculateSnapshot(vars.duration, vars.prior!.selections, vars.provider))
                .total_price
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
      setCalculationErrors((prev) => new Map(prev).set(vars.architectureId, errorMessageOf(err))),
    onSettled: (_data, _err, vars) => {
      markInFlight(vars.architectureId, false);
      // 021 (FR-016, FR-018a): a finished calculation of the open architecture — a result or an
      // error, Calculate or the automatic one — brings Pricing forward; a collapsed inspector
      // stays collapsed and marks its rail instead.
      if (vars.architectureId === architectureIdRef.current) {
        dispatchInspector({ type: "calculation-finished" });
        if (readColumnCollapsed().inspector) setNewResult(true);
      }
    },
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
        provider: pricingProvider,
      });
    },
    [
      architectureId,
      pricingProvider,
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
          arrowStyle: selectedConnector.arrow_style,
          arrowReversed: selectedConnector.arrow_reversed,
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
  const diagramSelection = useMemo<{
    kind: "collection" | "connector" | "service";
    id: string;
  } | null>(
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
    <div ref={rowRef} className="flex h-full w-full overflow-hidden">
      {!architecture.data && (
        <EmptyWorkspacePanels
          message={
            !architectureId
              ? "Open or create an architecture from the Cloud Pricing menu (the arrow beside Cloud Pricing above) to get started."
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
            onUpdateConnectorArrow={(id, change) => updateConnectorArrow.mutate({ id, change })}
            onPickSku={pickSkuFromSearch}
            searchNotice={searchNotice}
            searchRegion={searchRegion}
            provider={pricingProvider}
            regions={regions.data?.regions ?? []}
            onUpdateCollectionRegion={(id, region) => updateCollectionRegion.mutate({ id, region })}
            isUpdatingCollectionRegion={updateCollectionRegion.isPending}
            width={fitted.sidebar}
          />

          <ColumnResizeHandle
            ariaLabel="Resize Architecture Editor panel"
            onDrag={(dx) => resizeColumn("collections", dx)}
          />

          <div className="flex min-w-0 flex-1 flex-col gap-1.5 p-2">
            {/* 021 US5 (FR-005, FR-036): the open architecture's name, above the canvas. */}
            {architecture.data && (
              <h2 className="flex min-w-0 items-center text-sm font-semibold">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span tabIndex={0} aria-label={canvasTitle} className="truncate rounded-sm">
                      {canvasTitle}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>{canvasTitle}</TooltipContent>
                </Tooltip>
              </h2>
            )}
            <ArchitectureDiagramPanel
              architectureId={architectureId!}
              provider={pricingProvider}
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

          {!inspectorCollapsed && (
            <ColumnResizeHandle
              ariaLabel="Resize inspector"
              onDrag={(dx) => resizeColumn("inspector", -dx)}
            />
          )}

          {/* 021 (US2, US3): the Price Summary and the Service Editor as the inspector's tabs. */}
          <InspectorPanel
            arrangement={inspectorArrangement}
            onAction={dispatchInspector}
            collapsed={inspectorCollapsed}
            onCollapsedChange={setInspectorCollapsed}
            newResult={newResult}
            width={fitted.inspector}
            pricing={
              <PricingPanel
                duration={calculationDuration}
                onDurationChange={setCalculationDuration}
                onCalculate={() => startCalculation(calculationDuration)}
                isCalculating={isActiveCalculating}
                // As before 015, a result isn't shown while its own recalculation is running.
                calculation={isActiveCalculating ? null : (activeEntry?.result ?? null)}
                calculationError={(architectureId && calculationErrors.get(architectureId)) || null}
                onRetry={() => startCalculation(calculationDuration)}
                priceChange={activeEntry?.priceChange ?? null}
                priceChangeUnavailable={activeEntry?.priceChangeUnavailable === true}
                skuAttributesById={skuAttributesById}
                skuLabelsById={skuLabelsById}
                isOutOfDate={isOutOfDate && !isActiveCalculating}
              />
            }
            service={
              <ServiceConfigPanel
                selection={serviceConfigSelection}
                resolvedExisting={resolvedExistingSku}
                onSubmitNew={submitNewSku}
                onSubmitExisting={submitExistingSku}
                onRemoveExisting={removeExistingSku}
                actionError={skuActionError}
                onDismissActionError={() => setSkuActionError(null)}
                provider={pricingProvider}
              />
            }
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

      <RegionSelectDialog
        open={regionDialogOpen}
        onOpenChange={setRegionDialogOpen}
        regions={regions.data?.regions ?? []}
        providerName={PROVIDER_LABELS[pricingProvider]}
        onConfirm={(region) => createCollection.mutate({ region })}
        isSubmitting={createCollection.isPending}
      />

      {architecture.data && (
        <PopoutCanvasDialog
          open={popoutOpen}
          onOpenChange={setPopoutOpen}
          architectureId={architectureId!}
          provider={pricingProvider}
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
