import { PanelLeftClose, PanelLeftOpen, Plus, Cloud } from "lucide-react";
import { useState } from "react";

import type { ArchitectureSummary, Provider } from "../../api/client";
import { readColumnCollapsed, writeColumnCollapsed } from "../../lib/columnCollapse";
import { Button } from "../ui/button";
import { ScrollArea } from "../ui/scroll-area";
import { Separator } from "../ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import { ErrorMessage } from "../ErrorMessage";
import gcpIcon from "../../assets/providers/gcp_icon.png";
import azureIcon from "../../assets/providers/azure_icon.png";

// FR-008 (008-ui-updates-corrections, research.md §11): a provider's own icon in column 1's
// collapsed state, replacing the generic Lucide `Cloud` icon. AWS has no equivalent asset
// yet (spec Assumptions) — it keeps the generic icon until `aws_icon.png` is supplied; every
// other provider falls back the same way if a code isn't in this map.
const PROVIDER_ICONS: Record<string, string> = {
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
          <h3 className="px-1 text-2xs font-medium text-muted-foreground">
            {selectedProvider.toUpperCase()} Architectures
          </h3>
        )}

        {architecturesLoading && expanded && <p className="px-1 text-2xs">Loading…</p>}
        {architecturesError && expanded && (
          <ErrorMessage message={architecturesError} onRetry={onRetryArchitectures} />
        )}
        {!architecturesError && architectures.length === 0 && expanded && (
          <p className="px-1 text-2xs text-muted-foreground">No Architectures yet.</p>
        )}

        <ScrollArea className="min-h-0 flex-1">
          <ul className="flex flex-col gap-1 pr-2">
            {architectures.map((arch) =>
              expanded ? (
                <li key={arch.id} className="flex items-center gap-1">
                  <Button
                    variant={arch.id === selectedArchitectureId ? "secondary" : "ghost"}
                    className="flex-1 justify-start truncate"
                    size="sm"
                    onClick={() => onSelectArchitecture(arch.id)}
                  >
                    {arch.name}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Delete ${arch.name}`}
                    onClick={() => onDeleteArchitecture(arch.id)}
                  >
                    ✕
                  </Button>
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
          </ul>
        </ScrollArea>

        {/* FR-002: create control below the list, not above it. */}
        {expanded ? (
          <form
            className="mt-1 flex gap-1"
            onSubmit={(e) => {
              e.preventDefault();
              if (newArchitectureName.trim()) onCreateArchitecture();
            }}
          >
            <input
              className="min-w-0 flex-1 rounded border border-border bg-background px-1.5 py-1 text-2xs"
              value={newArchitectureName}
              onChange={(e) => onNewArchitectureNameChange(e.target.value)}
              placeholder="New Architecture name"
              aria-label="New Architecture name"
            />
            <Button type="submit" size="sm" disabled={isCreatingArchitecture}>
              Create
            </Button>
          </form>
        ) : (
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
