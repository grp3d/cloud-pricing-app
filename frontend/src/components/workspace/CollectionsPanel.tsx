import { Link2, Link2Off, Plus, Trash2 } from "lucide-react";

import type { CatalogSKU, CollectionType } from "../../api/client";
import { Button } from "../ui/button";
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
}

/**
 * Column 2 (007-ui-overhaul-shadcn, FR-003/004/005): Collection-creation controls and
 * Connect/Remove Connector actions stay fixed at the top; below, the current selection's own
 * name/delete control plus AWS-service search — deliberately no list of already-added
 * services (Clarifications) — an already-added service is reached only via the diagram
 * (column 4 → column 3).
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
}: CollectionsPanelProps) {
  return (
    <section className="flex h-full w-80 min-w-0 shrink-0 flex-col gap-3 overflow-hidden border-r border-border p-3">
      {/* Fixed section (FR-004): never scrolls out of view. */}
      <div className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">Collections &amp; Connectors</h2>
        <form
          className="flex flex-wrap items-center gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            if (newCollectionName.trim()) onAddCollection();
          }}
        >
          <select
            className="rounded border border-border bg-background px-1.5 py-1 text-sm"
            value={newCollectionType}
            onChange={(e) => onNewCollectionTypeChange(e.target.value as CollectionType)}
          >
            <option value="application_component">Application Component</option>
            <option value="vpc">VPC</option>
          </select>
          <input
            className="min-w-0 flex-1 rounded border border-border bg-background px-1.5 py-1 text-sm"
            placeholder="Collection name"
            value={newCollectionName}
            onChange={(e) => onNewCollectionNameChange(e.target.value)}
          />
          <Button type="submit" size="sm" disabled={!newCollectionName.trim() || isAddingCollection}>
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
        <ErrorMessage message={actionError} onRetry={onDismissActionError} retryLabel="Dismiss" />
      )}

      {/* Below the fixed section: current selection + search (FR-005). */}
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto">
        {!selection && (
          <p className="text-sm text-muted-foreground">
            Select a Collection or Connector on the diagram to search for AWS services.
          </p>
        )}

        {selection?.kind === "collection" && (
          <div className="flex items-center justify-between">
            <h3 className="font-medium">{selection.name}</h3>
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
              <h3 className="font-medium">Data Connector</h3>
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

        {selection && <CatalogSearchPanel onAdd={onPickSku} />}
      </div>
    </section>
  );
}
