import { Trash2 } from "lucide-react";

import type { SKUSelection } from "../../api/client";
import type { ServiceConfigSelection } from "../../lib/serviceConfigSelection";
import { Button } from "../ui/button";
import { ErrorMessage } from "../ErrorMessage";
import { PricingInputsForm, type PricingInputs } from "../PricingInputsForm";
import { SkuDetail } from "../SkuDetail";

export interface ServiceConfigPanelProps {
  selection: ServiceConfigSelection;
  /** The full SKUSelection object for a `"existing"` selection, resolved by `WorkspacePage`
   * (it already has the fetched Architecture data; this panel stays a simple consumer). */
  resolvedExisting: SKUSelection | null;
  onSubmitNew: (inputs: PricingInputs) => void;
  onSubmitExisting: (skuSelectionId: string, inputs: PricingInputs) => void;
  onRemoveExisting: (skuSelectionId: string) => void;
  actionError: string | null;
  onDismissActionError: () => void;
}

/**
 * Column 3 (007-ui-overhaul-shadcn, FR-005/012/015): a selected service's attributes and
 * pricing inputs — nothing else is shown here, and nothing is shown at all (this component
 * renders `null`) when `selection` is `null`, which is what makes the panel collapse entirely
 * rather than appearing as a visible-but-empty panel (Clarifications).
 */
export function ServiceConfigPanel({
  selection,
  resolvedExisting,
  onSubmitNew,
  onSubmitExisting,
  onRemoveExisting,
  actionError,
  onDismissActionError,
}: ServiceConfigPanelProps) {
  if (!selection) return null;

  // A stored `skuSelectionId` whose SKUSelection no longer exists (e.g. removed from another
  // tab) — collapse rather than render broken content; `WorkspacePage` also clears the
  // selection once this happens (see its removal handler).
  if (selection.kind === "existing" && !resolvedExisting) return null;

  const attributes =
    selection.kind === "new" ? selection.catalogSku.attributes : resolvedExisting!.attributes;
  const unit = selection.kind === "new" ? selection.catalogSku.unit : resolvedExisting!.unit;

  return (
    <aside className="flex h-full w-72 min-w-0 shrink-0 flex-col gap-3 overflow-auto border-r border-border p-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">
          {selection.kind === "new"
            ? `${selection.catalogSku.service_name} — ${selection.catalogSku.summary}`
            : `${resolvedExisting!.service_code} / ${resolvedExisting!.sku}`}
        </h3>
        {selection.kind === "existing" && (
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Remove this service"
            onClick={() => onRemoveExisting(resolvedExisting!.id)}
          >
            <Trash2 />
          </Button>
        )}
      </div>

      {actionError && (
        <ErrorMessage message={actionError} onRetry={onDismissActionError} retryLabel="Dismiss" />
      )}

      <SkuDetail attributes={attributes} />

      {selection.kind === "new" ? (
        <PricingInputsForm onSubmit={onSubmitNew} unit={unit} />
      ) : (
        <PricingInputsForm
          submitLabel="Save"
          initial={{
            pricing_term: resolvedExisting!.pricing_term,
            purchase_option: resolvedExisting!.purchase_option,
            usage_quantity: resolvedExisting!.usage_quantity,
          }}
          unit={unit}
          onSubmit={(inputs) => onSubmitExisting(resolvedExisting!.id, inputs)}
        />
      )}
    </aside>
  );
}
