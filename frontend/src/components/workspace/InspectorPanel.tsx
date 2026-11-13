import { Calculator, PanelRightClose, PanelRightOpen, SlidersHorizontal } from "lucide-react";
import type { ReactNode } from "react";

import {
  INSPECTOR_TABS,
  type InspectorAction,
  type InspectorArrangement,
  type InspectorTab,
} from "../../lib/inspectorLayout";
import { SplitTabPane } from "../layout/SplitTabPane";
import { Button } from "../ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

const TAB_LABELS: Record<InspectorTab, string> = { pricing: "Pricing", service: "Service" };

export interface InspectorPanelProps {
  arrangement: InspectorArrangement;
  onAction: (action: InspectorAction) => void;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  /** A calculation finished while collapsed (FR-018a): the rail's Pricing button is marked. */
  newResult: boolean;
  width: number;
  pricing: ReactNode;
  service: ReactNode;
}

/**
 * The workspace's right-hand inspector (021, US2 and US3): the Price Summary and the Service
 * Editor as two tabs, Pricing and Service.
 *
 * - **Merged:** one pane, one visible tab (FR-014).
 * - **Split:** an upper and a lower pane, one tab each, with a draggable divider (FR-019 to
 *   FR-021). Tabs are dragged with pointer events to the lower half (split or swap) or onto
 *   the upper tab bar (merge); each pane's tab options menu does the same from the keyboard
 *   (FR-022). Escape or a drop elsewhere cancels (FR-023).
 * - **Collapsed:** a narrow rail with a button per tab (FR-018a).
 *
 * Both tab bodies stay mounted in every arrangement, so unsaved Service input and the Pricing
 * tab's word-wrap choice survive tab switches, splits, merges and swaps (FR-017). The tabs
 * themselves are the shared `SplitTabPane` (023); every arrangement change goes through
 * `onAction`, which `WorkspacePage` feeds to `nextArrangement` (`inspectorLayout.ts`).
 */
export function InspectorPanel({
  arrangement,
  onAction,
  collapsed,
  onCollapsedChange,
  newResult,
  width,
  pricing,
  service,
}: InspectorPanelProps) {
  const collapseButton = (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Collapse inspector"
          className="ml-auto"
          onClick={() => onCollapsedChange(true)}
        >
          <PanelRightClose />
        </Button>
      </TooltipTrigger>
      <TooltipContent>Collapse</TooltipContent>
    </Tooltip>
  );

  const rail = (
    <div className="flex flex-col items-center gap-2 py-2">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Expand inspector"
            onClick={() => onCollapsedChange(false)}
          >
            <PanelRightOpen />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="left">Expand</TooltipContent>
      </Tooltip>
      {INSPECTOR_TABS.map((tab) => {
        const marked = tab === "pricing" && newResult;
        return (
          <Tooltip key={tab}>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={marked ? "Pricing — new result" : TAB_LABELS[tab]}
                className="relative"
                onClick={() => {
                  onAction({ type: "select-tab", tab });
                  onCollapsedChange(false);
                }}
              >
                {tab === "pricing" ? <Calculator /> : <SlidersHorizontal />}
                {marked && (
                  <span
                    aria-hidden
                    className="absolute top-1 right-1 size-2 rounded-full bg-primary"
                  />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent side="left">
              {marked ? "Pricing: a new result is waiting" : TAB_LABELS[tab]}
            </TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );

  return (
    <aside
      aria-label="Inspector"
      className="flex h-full shrink-0 flex-col border-l border-border bg-background"
      style={{ width: collapsed ? 56 : width }}
    >
      {collapsed && rail}
      {/* Always rendered, hidden while collapsed, so the bodies are never remounted. */}
      <SplitTabPane
        tabs={INSPECTOR_TABS}
        labels={TAB_LABELS}
        bodies={{ pricing, service }}
        arrangement={arrangement}
        onAction={onAction}
        name="inspector"
        hidden={collapsed}
        barEnd={collapseButton}
        scrollable
      />
    </aside>
  );
}
