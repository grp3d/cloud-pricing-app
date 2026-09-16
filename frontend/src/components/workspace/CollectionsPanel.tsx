import { Link2, Link2Off, PanelLeftClose, PanelLeftOpen, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import type { CatalogSKU, Collection, CollectionType, Region } from "../../api/client";
import { readColumnCollapsed, writeColumnCollapsed } from "../../lib/columnCollapse";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Separator } from "../ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import { CatalogSearchPanel } from "../CatalogSearchPanel";
import { ErrorMessage } from "../ErrorMessage";

/** 011-canvas-connector-popout, spec FR-002/FR-003: the connector-creation dialog, relocated
 * here verbatim from the canvas's own former `AddConnectorDialog`
 * (`ArchitectureDiagramPanel.tsx`) — same markup/validation, same `onCreateConnector` mutation
 * (research.md §2). The only new behavior is pre-population (FR-005): opening the dialog seeds
 * "From"/"To" from whichever Collections are currently selected on the canvas, in selection
 * order, only for the 0/1/2-selected cases — more than two leaves both empty, same as zero. */
function ConnectDialog({
  collections,
  selectedNodeIds,
  onCreateConnector,
}: {
  collections: Collection[];
  selectedNodeIds: string[];
  onCreateConnector: (from: string, to: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState<string | undefined>(undefined);
  const [to, setTo] = useState<string | undefined>(undefined);

  // FR-026a (009): the same Collection can't be chosen in both dropdowns.
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

  // FR-005: pre-populate from the canvas's current multi-selection, in selection order, only
  // for the 0/1/2-selected cases (more than two leaves both empty, same as zero). This has to
  // run from the *trigger* button's own click, not `Dialog`'s `onOpenChange` — Radix only
  // calls `onOpenChange` for transitions it initiates itself (Escape, overlay/outside click,
  // `DialogClose`), not when a parent externally flips the `open` prop via a plain sibling
  // button click like this one (found live: `onOpenChange`'s open-path was simply never
  // reached from this button, so pre-population silently never ran).
  function handleOpenClick() {
    if (selectedNodeIds.length === 1) {
      setFrom(selectedNodeIds[0]);
      setTo(undefined);
    } else if (selectedNodeIds.length === 2) {
      setFrom(selectedNodeIds[0]);
      setTo(selectedNodeIds[1]);
    } else {
      reset();
    }
    setOpen(true);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={handleOpenClick}
        title="Connect two Collections"
      >
        <Link2 /> Connect
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
  );
}

export type CollectionsPanelSelection =
  | { kind: "collection"; id: string; name: string; region: string; locked: boolean }
  | { kind: "connector"; id: string; attachedSkuSummary: string | null }
  | null;

export interface CollectionsPanelProps {
  newCollectionType: CollectionType;
  onNewCollectionTypeChange: (type: CollectionType) => void;
  newCollectionName: string;
  onNewCollectionNameChange: (name: string) => void;
  onAddCollection: () => void;
  isAddingCollection: boolean;

  /** 011-canvas-connector-popout, spec FR-003/FR-005: the full Collections list (for the
   * relocated Connect dialog's From/To dropdowns) and the canvas's currently-selected node
   * ids, in selection order (for pre-populating them) — replaces the prior `canConnect`/
   * `onConnect` (which gated an immediate-connect action rather than opening a dialog). */
  collections: Collection[];
  selectedNodeIds: string[];
  onCreateConnector: (from: string, to: string) => void;
  hasSelectedConnector: boolean;
  onRemoveConnector: () => void;

  actionError: string | null;
  onDismissActionError: () => void;

  selection: CollectionsPanelSelection;
  onDeleteCollection: (id: string) => void;
  onDeleteConnector: (id: string) => void;
  onPickSku: (sku: CatalogSKU) => void;
  /** 010-multi-region-support, spec FR-005/FR-006: region to scope "Add a Service" search to —
   * the selected collection's region, or a selected connector's "from" collection's region. */
  searchRegion: string | undefined;
  /** 010-multi-region-support, spec FR-003/FR-017: the region control on a selected
   * collection — the available-regions list, the change handler, and its pending state. */
  regions: Region[];
  onUpdateCollectionRegion: (id: string, region: string) => void;
  isUpdatingCollectionRegion: boolean;
  /** Expanded-state width in pixels (FR-012/013, 008-ui-updates-corrections) — draggable
   * and persisted by `WorkspacePage`; ignored while collapsed, which always uses the rail
   * width below. */
  width: number;
}

/**
 * Column 2 (008-ui-updates-corrections, FR-006/009/010): header "Architecture Editor";
 * three sections — "Collections" (creation controls + Connect/Remove Connector, fixed at
 * the top, unchanged from 007's FR-004 behavior), "Selected Collection" (the current
 * selection's own name/delete control), "Add a Service" (the search panel) — each
 * separated by a visible divider that stays visible even when the section it borders has
 * no content (FR-010). Collapsible to an icon rail (FR-006), mirroring
 * `ProviderArchitecturePanel.tsx`'s 007 pattern. Deliberately no list of already-added
 * services (007, Clarifications) — an already-added service is reached only via the
 * diagram (column 4 → column 3).
 */
export function CollectionsPanel({
  newCollectionType,
  onNewCollectionTypeChange,
  newCollectionName,
  onNewCollectionNameChange,
  onAddCollection,
  isAddingCollection,
  collections,
  selectedNodeIds,
  onCreateConnector,
  hasSelectedConnector,
  onRemoveConnector,
  actionError,
  onDismissActionError,
  selection,
  onDeleteCollection,
  onDeleteConnector,
  onPickSku,
  searchRegion,
  regions,
  onUpdateCollectionRegion,
  isUpdatingCollectionRegion,
  width,
}: CollectionsPanelProps) {
  // 009-ui-fixes-next-iteration follow-up: collapsed/expanded state now survives a reload,
  // the same per-browser `localStorage` mechanism `columnWidths.ts` already uses for this
  // column's width — initialized lazily so the very first render already reflects it (no
  // expand-then-collapse flash).
  const [expanded, setExpanded] = useState(() => !readColumnCollapsed().collections);

  function toggleExpanded() {
    setExpanded((v) => {
      const next = !v;
      writeColumnCollapsed("collections", !next);
      return next;
    });
  }

  return (
    <section
      className="flex h-full min-w-0 shrink-0 flex-col gap-3 overflow-hidden border-r border-border p-2 transition-[width]"
      style={{ width: expanded ? width : 56 }}
    >
      <div className={`flex items-center ${expanded ? "justify-between" : "justify-center"}`}>
        {expanded && <h2 className="text-2xs font-semibold">Architecture Editor</h2>}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={expanded ? "Collapse panel" : "Expand panel"}
              onClick={toggleExpanded}
            >
              {expanded ? <PanelLeftClose /> : <PanelLeftOpen />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{expanded ? "Collapse" : "Expand"}</TooltipContent>
        </Tooltip>
      </div>

      {expanded && (
        <>
          {/* "Collections" section (FR-009) — fixed, never scrolls out of view (FR-004,
              unchanged from 007). */}
          <div className="flex flex-col gap-2">
            <h3 className="text-2xs font-medium text-muted-foreground">Collections</h3>
            <form
              className="flex flex-wrap items-center gap-1.5"
              onSubmit={(e) => {
                e.preventDefault();
                if (newCollectionName.trim()) onAddCollection();
              }}
            >
              <select
                className="rounded border border-border bg-background px-1.5 py-1 text-2xs"
                value={newCollectionType}
                onChange={(e) => onNewCollectionTypeChange(e.target.value as CollectionType)}
              >
                {/* 010-multi-region-support, spec FR-010: "Application" (not "Application
                    Component") — shorter, freeing horizontal space for the collection name. */}
                <option value="application_component">Application</option>
                <option value="vpc">VPC</option>
              </select>
              <input
                className="min-w-0 flex-1 rounded border border-border bg-background px-1.5 py-1 text-2xs"
                placeholder="Collection name"
                value={newCollectionName}
                onChange={(e) => onNewCollectionNameChange(e.target.value)}
              />
              <Button
                type="submit"
                size="sm"
                disabled={!newCollectionName.trim() || isAddingCollection}
              >
                <Plus /> Add
              </Button>
            </form>
            <div className="flex gap-1.5">
              <ConnectDialog
                collections={collections}
                selectedNodeIds={selectedNodeIds}
                onCreateConnector={onCreateConnector}
              />
              <Button
                variant="outline"
                size="sm"
                onClick={onRemoveConnector}
                disabled={!hasSelectedConnector}
                title="Select a connector on the diagram to remove it"
              >
                <Link2Off /> Remove Connector
              </Button>
            </div>
          </div>

          {actionError && (
            <ErrorMessage
              message={actionError}
              onRetry={onDismissActionError}
              retryLabel="Dismiss"
            />
          )}

          <Separator />

          {/* "Selected Collection" section (FR-009) — stays present, with a placeholder,
              even when nothing is selected (FR-010: the separators bracketing it never
              disappear). */}
          <div className="flex flex-col gap-2">
            <h3 className="text-2xs font-medium text-muted-foreground">Selected Collection</h3>
            {!selection && (
              <p className="text-2xs text-muted-foreground">
                Select a Collection or Connector on the diagram.
              </p>
            )}
            {selection?.kind === "collection" && (
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <h4 className="font-medium">{selection.name}</h4>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Delete Collection"
                    onClick={() => onDeleteCollection(selection.id)}
                  >
                    <Trash2 />
                  </Button>
                </div>
                {/* 010-multi-region-support, spec FR-003: editable while the collection has no
                    content, locked (disabled) once it does — enforced server-side too. */}
                <div className="flex items-center gap-1.5">
                  <span className="text-2xs text-muted-foreground">Region</span>
                  <Select
                    value={selection.region}
                    onValueChange={(region) => onUpdateCollectionRegion(selection.id, region)}
                    disabled={selection.locked || isUpdatingCollectionRegion}
                  >
                    <SelectTrigger className="h-6 w-full text-2xs" aria-label="Collection region">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {regions.map((r) => (
                        <SelectItem key={r.code} value={r.code}>
                          {r.code}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {selection.locked && (
                  <p className="text-2xs text-muted-foreground">
                    Region is locked because this collection already has content.
                  </p>
                )}
              </div>
            )}
            {selection?.kind === "connector" && (
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium">Data Connector</h4>
                  <p className="text-2xs text-muted-foreground">
                    {selection.attachedSkuSummary
                      ? `Attached service: ${selection.attachedSkuSummary}`
                      : "No connecting service attached (optional — e.g. a NAT/Internet/Transit Gateway)."}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Delete this Data Connector"
                  onClick={() => onDeleteConnector(selection.id)}
                >
                  <Trash2 />
                </Button>
              </div>
            )}
          </div>

          <Separator />

          {/* "Add a Service" section (FR-009) — the search panel; stays present, with a
              placeholder, even when nothing is selected to search on behalf of.
              `overflow-hidden` (not `-auto`): `CatalogSearchPanel` now owns its own internal
              scroll region so its filter row can stay fixed while only its results list
              scrolls (FR-022) — a second scroll container here would fight that. */}
          <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden">
            <h3 className="shrink-0 text-2xs font-medium text-muted-foreground">Add a Service</h3>
            {selection ? (
              <CatalogSearchPanel onAdd={onPickSku} region={searchRegion} />
            ) : (
              <p className="text-2xs text-muted-foreground">
                Select a Collection or Connector first.
              </p>
            )}
          </div>
        </>
      )}
    </section>
  );
}
