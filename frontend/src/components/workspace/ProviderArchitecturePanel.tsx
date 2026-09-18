import { PanelLeftClose, PanelLeftOpen, Plus, Cloud, Users, Download } from "lucide-react";
import { useState } from "react";

import type { ArchitectureSummary, Provider } from "../../api/client";
import { readColumnCollapsed, writeColumnCollapsed } from "../../lib/columnCollapse";
import { Button } from "../ui/button";
import { Separator } from "../ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import { ErrorMessage } from "../ErrorMessage";
import awsIcon from "../../assets/providers/aws_icon.png";
import gcpIcon from "../../assets/providers/gcp_icon.png";
import azureIcon from "../../assets/providers/azure_icon.png";

// FR-008 (008-ui-updates-corrections, research.md §11): a provider's own icon in column 1's
// collapsed state, replacing the generic Lucide `Cloud` icon. Every provider falls back to
// the generic icon if its code isn't in this map (009-ui-fixes-next-iteration follow-up:
// `aws_icon.png` supplied, closing the one gap this map used to have).
const PROVIDER_ICONS: Record<string, string> = {
  aws: awsIcon,
  gcp: gcpIcon,
  azure: azureIcon,
};

export interface ProviderArchitecturePanelProps {
  providers: Provider[];
  selectedProvider: string;
  onSelectProvider: (code: string) => void;
  architectures: ArchitectureSummary[];
  architecturesLoading: boolean;
  architecturesError: string | null;
  onRetryArchitectures: () => void;
  selectedArchitectureId: string | undefined;
  onSelectArchitecture: (id: string) => void;
  newArchitectureName: string;
  onNewArchitectureNameChange: (name: string) => void;
  onCreateArchitecture: () => void;
  isCreatingArchitecture: boolean;
  onDeleteArchitecture: (id: string) => void;
  actionError: string | null;
  onDismissActionError: () => void;
  /** Expanded-state width in pixels (FR-012/013, 008-ui-updates-corrections) — draggable
   * and persisted by `WorkspacePage`; ignored while collapsed, which always uses the rail
   * width below. */
  width: number;
  /** 012-user-accounts-sharing, spec FR-022/FR-027: the sharing icon and Import action never
   * appear for a guest identity — guest architectures can never be public. */
  isGuest: boolean;
  onToggleArchitecturePublic: (id: string, isPublic: boolean) => void;
  onOpenImportDialog: () => void;
}

/**
 * Column 1 (007-ui-overhaul-shadcn, FR-001/002/016/017): provider + Architecture selection
 * and creation, replacing the old standalone landing page. Collapsible to an icon-only rail
 * (Clarifications) — collapse state now survives a reload (009-ui-fixes-next-iteration
 * follow-up; superseding 007's "local, non-persisted" choice), via the same per-browser
 * `localStorage` mechanism `columnWidths.ts` already uses for this column's width.
 */
export function ProviderArchitecturePanel({
  providers,
  selectedProvider,
  onSelectProvider,
  architectures,
  architecturesLoading,
  architecturesError,
  onRetryArchitectures,
  selectedArchitectureId,
  onSelectArchitecture,
  newArchitectureName,
  onNewArchitectureNameChange,
  onCreateArchitecture,
  isCreatingArchitecture,
  onDeleteArchitecture,
  actionError,
  onDismissActionError,
  width,
  isGuest,
  onToggleArchitecturePublic,
  onOpenImportDialog,
}: ProviderArchitecturePanelProps) {
  const [expanded, setExpanded] = useState(() => !readColumnCollapsed().provider);

  function toggleExpanded() {
    setExpanded((v) => {
      const next = !v;
      writeColumnCollapsed("provider", !next);
      return next;
    });
  }

  return (
    <aside
      className="flex h-full shrink-0 flex-col gap-3 overflow-hidden border-r border-border p-2 transition-[width]"
      style={{ width: expanded ? width : 56 }}
    >
      <div className={`flex items-center ${expanded ? "justify-between" : "justify-center"}`}>
        {expanded && <h2 className="text-2xs font-semibold">Cloud Pricing</h2>}
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

      <Separator />

      <section aria-label="Cloud providers" className="flex flex-col gap-1">
        {expanded && (
          <h3 className="px-1 text-2xs font-medium text-muted-foreground">Providers</h3>
        )}
        <div className={`flex flex-col gap-1.5`}>
          {providers.map((p) =>
            expanded ? (
              <Button
                key={p.code}
                variant={p.code === selectedProvider ? "default" : "outline"}
                size="sm"
                disabled={!p.active}
                aria-pressed={p.code === selectedProvider}
                onClick={() => p.active && onSelectProvider(p.code)}
                className="justify-start"
              >
                {p.name}
              </Button>
            ) : (
              <Tooltip key={p.code}>
                <TooltipTrigger asChild>
                  <Button
                    variant={p.code === selectedProvider ? "default" : "outline"}
                    size="icon-sm"
                    disabled={!p.active}
                    aria-pressed={p.code === selectedProvider}
                    aria-label={p.name}
                    onClick={() => p.active && onSelectProvider(p.code)}
                  >
                    {PROVIDER_ICONS[p.code] ? (
                      <img src={PROVIDER_ICONS[p.code]} alt="" className="size-4" />
                    ) : (
                      <Cloud />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right">{p.name}</TooltipContent>
              </Tooltip>
            ),
          )}
        </div>
      </section>

      <Separator />

      {actionError && (
        <ErrorMessage message={actionError} onRetry={onDismissActionError} retryLabel="Dismiss" />
      )}

      <section aria-label="Architectures" className="flex min-h-0 flex-1 flex-col gap-1">
        {expanded && (
          <div className="flex items-center justify-between px-1">
            <h3 className="text-2xs font-medium text-muted-foreground">
              {selectedProvider.toUpperCase()} Architectures
            </h3>
            {!isGuest && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    aria-label="Import an architecture"
                    onClick={onOpenImportDialog}
                  >
                    <Download />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Import</TooltipContent>
              </Tooltip>
            )}
          </div>
        )}

        {architecturesLoading && expanded && <p className="px-1 text-2xs">Loading…</p>}
        {architecturesError && expanded && (
          <ErrorMessage message={architecturesError} onRetry={onRetryArchitectures} />
        )}
        {!architecturesError && architectures.length === 0 && expanded && (
          <p className="px-1 text-2xs text-muted-foreground">No Architectures yet.</p>
        )}

        {/* A plain scrolling div, not the shared ScrollArea/Radix primitive: Radix's
         * ScrollArea always wraps its content in an internal `display: table;
         * min-width: 100%` node so it can measure true content size for its custom
         * scrollbar thumb -- that wrapper sizes itself to this list's *unwrapped* natural
         * width, which defeats `flex-wrap` on the rows below (their container is never
         * actually narrower than their unwrapped content, so wrapping never triggers).
         * A plain overflow-y-auto div has no such quirk and lets flex-wrap work. */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          <ul className="flex flex-col gap-1 pr-2">
            {architectures.map((arch) =>
              expanded ? (
                <li key={arch.id} className="flex flex-wrap items-start gap-1">
                  <Button
                    variant={arch.id === selectedArchitectureId ? "secondary" : "ghost"}
                    className="h-auto min-w-0 flex-1 justify-start whitespace-normal break-words py-1 text-left"
                    size="sm"
                    onClick={() => onSelectArchitecture(arch.id)}
                  >
                    {arch.name}
                  </Button>
                  {!isGuest && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={
                            arch.is_public
                              ? `Make ${arch.name} private`
                              : `Make ${arch.name} public`
                          }
                          onClick={() => onToggleArchitecturePublic(arch.id, !arch.is_public)}
                        >
                          <Users
                            className={
                              arch.is_public
                                ? "rounded-sm border border-green-500"
                                : "rounded-sm border border-transparent"
                            }
                          />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        {arch.is_public ? "Click to make private" : "Click to make public"}
                      </TooltipContent>
                    </Tooltip>
                  )}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Delete ${arch.name}`}
                        className="text-destructive hover:text-destructive"
                        onClick={() => onDeleteArchitecture(arch.id)}
                      >
                        ✕
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Click to remove</TooltipContent>
                  </Tooltip>
                </li>
              ) : (
                <li key={arch.id}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant={arch.id === selectedArchitectureId ? "secondary" : "ghost"}
                        size="icon-sm"
                        aria-label={arch.name}
                        onClick={() => onSelectArchitecture(arch.id)}
                      >
                        {arch.name.charAt(0).toUpperCase()}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="right">{arch.name}</TooltipContent>
                  </Tooltip>
                </li>
              ),
            )}

            {/* Follow-up fix: the create control lives inside the scrollable list itself
             * (not as a sibling after it) so it always sits directly under the last
             * architecture — a sibling with a flex-1 ScrollArea above it would instead get
             * pushed to the bottom of the whole column, leaving a gap when the list is short. */}
            {expanded && (
              <li>
                <form
                  className="mt-1 flex flex-wrap gap-1"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (newArchitectureName.trim()) onCreateArchitecture();
                  }}
                >
                  <input
                    className="min-w-[3rem] flex-1 rounded border border-border bg-background px-1.5 py-1 text-2xs"
                    value={newArchitectureName}
                    onChange={(e) => onNewArchitectureNameChange(e.target.value)}
                    placeholder="New Architecture name"
                    aria-label="New Architecture name"
                  />
                  <Button type="submit" size="sm" disabled={isCreatingArchitecture}>
                    Create
                  </Button>
                </form>
              </li>
            )}
          </ul>
        </div>

        {!expanded && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="icon-sm"
                aria-label="New Architecture"
                onClick={() => setExpanded(true)}
              >
                <Plus />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">New Architecture</TooltipContent>
          </Tooltip>
        )}
      </section>
    </aside>
  );
}
