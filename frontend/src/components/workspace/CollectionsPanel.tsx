import { Link2, Link2Off, PanelLeftClose, PanelLeftOpen, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import type { CatalogSKU, CollectionType } from "../../api/client";
import { Button } from "../ui/button";
import { Separator } from "../ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import { CatalogSearchPanel } from "../CatalogSearchPanel";
import { ErrorMessage } from "../ErrorMessage";

export type CollectionsPanelSelection =
  | { kind: "collection"; id: string; name: string }
  | { kind: "connector"; id: string; attachedSkuSummary: string | null }
  | null;

export interface CollectionsPanelProps {
  newCollectionType: CollectionType;
  onNewCollectionTypeChange: (type: CollectionType) => void;
  newCollectionName: string;
  onNewCollectionNameChange: (name: string) => void;
  onAddCollection: () => void;
  isAddingCollection: boolean;

  canConnect: boolean;
  onConnect: () => void;
  hasSelectedConnector: boolean;
  onRemoveConnector: () => void;

  actionError: string | null;
  onDismissActionError: () => void;

  selection: CollectionsPanelSelection;
  onDeleteCollection: (id: string) => void;
  onDeleteConnector: (id: string) => void;
  onPickSku: (sku: CatalogSKU) => void;
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
  canConnect,
  onConnect,
  hasSelectedConnector,
  onRemoveConnector,
  actionError,
  onDismissActionError,
  selection,
  onDeleteCollection,
  onDeleteConnector,
  onPickSku,
  width,
}: CollectionsPanelProps) {
  const [expanded, setExpanded] = useState(true);

  return (
    <section
      className="flex h-full min-w-0 shrink-0 flex-col gap-3 overflow-hidden border-r border-border p-2 transition-[width]"
      style={{ width: expanded ? width : 56 }}
    >
      <div className={`flex items-center ${expanded ? "justify-between" : "justify-center"}`}>
        {expanded && <h2 className="text-xs font-semibold">Architecture Editor</h2>}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={expanded ? "Collapse panel" : "Expand panel"}
              onClick={() => setExpanded((v) => !v)}
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
            <h3 className="text-xs font-medium text-muted-foreground">Collections</h3>
            <form
              className="flex flex-wrap items-center gap-1.5"
              onSubmit={(e) => {
                e.preventDefault();
                if (newCollectionName.trim()) onAddCollection();
              }}
            >
              <select
                className="rounded border border-border bg-background px-1.5 py-1 text-xs"
                value={newCollectionType}
                onChange={(e) => onNewCollectionTypeChange(e.target.value as CollectionType)}
              >
                <option value="application_component">Application Component</option>
                <option value="vpc">VPC</option>
              </select>
              <input
                className="min-w-0 flex-1 rounded border border-border bg-background px-1.5 py-1 text-xs"
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
              <Button
                variant="outline"
                size="sm"
                onClick={onConnect}
                disabled={!canConnect}
                title="Select exactly two boxes on the diagram to connect them"
              >
                <Link2 /> Connect
              </Button>
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
            <h3 className="text-xs font-medium text-muted-foreground">Selected Collection</h3>
            {!selection && (
              <p className="text-xs text-muted-foreground">
                Select a Collection or Connector on the diagram.
              </p>
            )}
            {selection?.kind === "collection" && (
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
            )}
            {selection?.kind === "connector" && (
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium">Data Connector</h4>
                  <p className="text-xs text-muted-foreground">
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
            <h3 className="shrink-0 text-xs font-medium text-muted-foreground">Add a Service</h3>
            {selection ? (
              <CatalogSearchPanel onAdd={onPickSku} />
            ) : (
              <p className="text-xs text-muted-foreground">
                Select a Collection or Connector first.
              </p>
            )}
          </div>
        </>
      )}
    </section>
  );
}
