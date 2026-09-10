import type { CatalogSKU } from "../api/client";

/**
 * What the service-configuration panel (column 3) shows, if anything
 * (007-ui-overhaul-shadcn, FR-005/FR-012/FR-015). Replaces this app's previous two separate
 * pieces of state — `pickedSku` (a catalog result chosen to add) and `editingSkuSelectionId`
 * (an existing SKU Selection being edited) — with one slot, so "at most one service's
 * configuration at a time, selecting a different one replaces it" (FR-015) is a structural
 * property of assigning this single value, not a convention two states must be kept in sync
 * to honor. `null` means the panel is collapsed (FR-012) — nothing is selected.
 */
export type ServiceConfigSelection =
  | { kind: "existing"; skuSelectionId: string }
  | { kind: "new"; catalogSku: CatalogSKU }
  | null;

/** A service already placed in a Collection or Data Connector, selected by clicking it on
 * the diagram (or a Data Connector's own already-attached service — research.md §8). */
export function existingServiceSelection(skuSelectionId: string): ServiceConfigSelection {
  return { kind: "existing", skuSelectionId };
}

/** A catalog SKU just picked from search results, not yet added to anything. */
export function newServiceSelection(catalogSku: CatalogSKU): ServiceConfigSelection {
  return { kind: "new", catalogSku };
}
