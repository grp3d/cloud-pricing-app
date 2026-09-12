import { PanelLeftClose, PanelLeftOpen, Trash2 } from "lucide-react";
import { useState } from "react";

import type { SKUSelection } from "../../api/client";
import type { ServiceConfigSelection } from "../../lib/serviceConfigSelection";
import { Button } from "../ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
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
  /** Expanded-state width in pixels (FR-012/013, 008-ui-updates-corrections) — draggable
   * and persisted by `WorkspacePage`; ignored while collapsed, which always uses the rail
   * width below. */
  width: number;
}

/**
 * Column 3 (008-ui-updates-corrections, FR-005/006/011): always present, at its normal
 * width, regardless of what is selected — supersedes 007's FR-012, which collapsed this
 * panel to zero width when nothing was selected (the resulting sideways content-shift on
 * every service selection/deselection was itself the correction this feature makes, per
 * spec User Story 2's "Why this priority"). When no service is selected, only the panel's
 * own chrome (header, collapse control, border) renders — no service content. Collapsible
 * to an icon rail (FR-006), mirroring `ProviderArchitecturePanel.tsx`'s 007 pattern exactly.
 */
export function ServiceConfigPanel({
  selection,
  resolvedExisting,
  onSubmitNew,
  onSubmitExisting,
  onRemoveExisting,
  actionError,
  onDismissActionError,
  width,
}: ServiceConfigPanelProps) {
  const [expanded, setExpanded] = useState(true);

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

  return (
    <aside
      className="flex h-full min-w-0 shrink-0 flex-col gap-3 overflow-hidden border-r border-border p-2 transition-[width]"
      style={{ width: expanded ? width : 56 }}
    >
      <div className={`flex items-center ${expanded ? "justify-between" : "justify-center"}`}>
        {expanded && <h2 className="text-2xs font-semibold">Service Editor</h2>}
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

      {expanded && !hasContent && (
        <p className="text-2xs text-muted-foreground">
          Select a service on the diagram, or add one from column 2, to configure it here.
        </p>
      )}

      {expanded && hasContent && (
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto">
          <div className="flex items-center justify-between">
            <h3 className="text-2xs font-semibold">
              {selection!.kind === "new"
                ? `${selection!.catalogSku.service_name} — ${selection!.catalogSku.summary}`
                : `${resolvedExisting!.service_code} / ${resolvedExisting!.sku}`}
            </h3>
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

          {actionError && (
            <ErrorMessage
              message={actionError}
              onRetry={onDismissActionError}
              retryLabel="Dismiss"
            />
          )}

          <SkuDetail attributes={attributes!} />

          {selection!.kind === "new" ? (
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
        </div>
      )}
    </aside>
  );
}
