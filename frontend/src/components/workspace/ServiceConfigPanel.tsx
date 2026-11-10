import { Trash2 } from "lucide-react";

import type { ProviderCode, SKUSelection } from "../../api/client";
import type { ServiceConfigSelection } from "../../lib/serviceConfigSelection";
import { serviceLabel } from "../../lib/serviceLabel";
import { summarizeAttributes } from "../../lib/skuDetail";
import { Button } from "../ui/button";
import { Separator } from "../ui/separator";
import { ErrorMessage } from "../ErrorMessage";
import { PricingInputsForm, type PricingInputs } from "../PricingInputsForm";
import { SkuDetail } from "../SkuDetail";

export interface ServiceConfigPanelProps {
  selection: ServiceConfigSelection;
  /** The full SKUSelection object for a `"existing"` selection, resolved by `WorkspacePage`
   * (it already has the fetched Architecture data; this panel stays a simple consumer). */
  resolvedExisting: SKUSelection | null;
  onSubmitNew: (inputs: PricingInputs) => void;
  /** Resolves to `false` when the save failed (021 US5: Save then stays dark blue). */
  onSubmitExisting: (
    skuSelectionId: string,
    inputs: PricingInputs,
  ) => void | boolean | Promise<void | boolean>;
  onRemoveExisting: (skuSelectionId: string) => void;
  actionError: string | null;
  onDismissActionError: () => void;
  /** 019 (FR-005a): the architecture's provider picks the editor's provider fields. */
  provider?: ProviderCode;
}

/**
 * Column 3 (008-ui-updates-corrections, FR-005/006/011): always present, at its normal
 * width, regardless of what is selected — supersedes 007's FR-012, which collapsed this
 * panel to zero width when nothing was selected (the resulting sideways content-shift on
 * every service selection/deselection was itself the correction this feature makes, per
 * spec User Story 2's "Why this priority"). When no service is selected, only the panel's
 * own chrome (header, collapse control, border) renders — no service content.
 *
 * 021 (FR-013, FR-018): the inspector's Service tab body. The inspector owns the width and
 * the collapse; with nothing selected this shows "Select a service on the canvas".
 */
export function ServiceConfigPanel({
  selection,
  resolvedExisting,
  onSubmitNew,
  onSubmitExisting,
  onRemoveExisting,
  actionError,
  onDismissActionError,
  provider = "aws",
}: ServiceConfigPanelProps) {
  // A stored `skuSelectionId` whose SKUSelection no longer exists (e.g. removed from another
  // tab) — treat as nothing selected rather than rendering broken content; `WorkspacePage`
  // also clears the selection once this happens (see its removal handler).
  const hasContent = Boolean(selection && !(selection.kind === "existing" && !resolvedExisting));

  const attributes =
    selection?.kind === "new"
      ? selection.catalogSku.attributes
      : hasContent
        ? resolvedExisting!.attributes
        : undefined;
  const unit =
    selection?.kind === "new"
      ? selection.catalogSku.unit
      : hasContent
        ? resolvedExisting!.unit
        : undefined;
  // 019 (FR-005): what the item publishes and what kind of item it is, from the catalog (a new
  // service) or the stored selection's resolved details (an existing one).
  const item =
    selection?.kind === "new" ? selection.catalogSku : hasContent ? resolvedExisting! : undefined;

  // 021 US7 (FR-046): a readable heading (the service's name and description), with the codes
  // muted below it. AWS has no provider name on a saved service, so its heading is the service
  // code and its identifying details, as on the canvas.
  const label = hasContent
    ? serviceLabel(selection!.kind === "new" ? selection!.catalogSku : resolvedExisting!)
    : null;
  const description =
    label && (label.description ?? (summarizeAttributes(attributes ?? {}) || null));
  // GCP's saved items carry little beyond their location, so its category path is listed too.
  const productFamily = item && "product_family" in item ? item.product_family : null;
  const detailAttributes =
    provider === "gcp" && productFamily ? { category: productFamily, ...attributes } : attributes;

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      {!hasContent && (
        <div className="flex flex-col gap-1 p-3 text-2xs text-muted-foreground">
          <p className="text-xs font-medium text-foreground">Select a service on the canvas</p>
          <p>Or pick one in the Architecture Editor's service search to add it.</p>
        </div>
      )}

      {/* 021 US8 (FR-049): the heading (name, description, codes) and the delete button stay
          pinned above a divider; the details and the form scroll on their own. */}
      {hasContent && (
        <>
          <div data-testid="service-pinned" className="flex shrink-0 flex-col gap-2 px-3 pt-3">
            <div className="flex items-start justify-between gap-2">
              <div className="flex min-w-0 flex-col gap-0.5">
                <h3 className="text-xs font-semibold break-words">
                  {label!.name}
                  {description && (
                    <span className="block font-normal text-foreground">{description}</span>
                  )}
                </h3>
                <p className="text-2xs break-all text-muted-foreground">{label!.codes}</p>
              </div>
              {selection!.kind === "existing" && (
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
            <Separator />
          </div>

          <div
            data-testid="service-scroll"
            className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-3"
          >
            {actionError && (
              <ErrorMessage
                message={actionError}
                onRetry={onDismissActionError}
                retryLabel="Dismiss"
              />
            )}

            <SkuDetail attributes={detailAttributes!} />

            {/* Live user report (regression): editing one service's usage quantity was landing
              on a *different* service instead. Root cause — `PricingInputsForm`'s `term`/
              `purchaseOption`/`quantity` are seeded via `useState(initial?.field ?? default)`,
              which only runs once, on mount. Neither usage below ever had a `key`, so
              switching the selected service (this panel re-renders with new `selection`/
              `resolvedExisting` props, same component *instance*) reused the previous
              service's already-mounted form untouched — its fields kept showing whatever was
              last typed for the *previous* service. Saving without first retyping every field
              then submitted that leftover value against the *newly* selected service's id
              (`onSubmitExisting`/`onSubmitNew` below are correctly scoped to the current
              selection already — this was never a wrong-id bug, purely stale-input state).
              `key` forces React to unmount/remount with fresh `useState` initializers whenever
              the underlying service identity actually changes, the standard fix for exactly
              this "state needs to reset when an identity prop changes" case. */}
            {selection!.kind === "new" ? (
              <PricingInputsForm
                key={`new-${selection!.catalogSku.service_code}-${selection!.catalogSku.sku}`}
                onSubmit={onSubmitNew}
                unit={unit}
                provider={provider}
                priceTypes={item?.price_types}
                kind={item?.kind}
                attributes={attributes}
              />
            ) : (
              <PricingInputsForm
                key={resolvedExisting!.id}
                submitLabel="Save"
                initial={{
                  pricing_term: resolvedExisting!.pricing_term,
                  purchase_option: resolvedExisting!.purchase_option,
                  usage_quantity: resolvedExisting!.usage_quantity,
                  provider_options: resolvedExisting!.provider_options ?? null,
                }}
                unit={unit}
                provider={provider}
                priceTypes={item?.price_types}
                kind={item?.kind}
                attributes={attributes}
                onSubmit={(inputs) => onSubmitExisting(resolvedExisting!.id, inputs)}
              />
            )}
          </div>
        </>
      )}
    </div>
  );
}
