import { ChevronRight, Download, Pencil, Plus, Users } from "lucide-react";
import { forwardRef, useRef, useState } from "react";

import type {
  ArchitectureLibrary,
  ProviderArchitectures,
} from "../../hooks/useArchitectureLibrary";
import {
  IMPORT_ARCHITECTURE_LABELS,
  PROVIDER_LABELS,
  asProviderCode,
  providerHint,
} from "../../lib/providerPricing";
import { ErrorMessage } from "../ErrorMessage";
import { Button } from "../ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

/** Marks the per-group name field, so the popover can tell an Escape meant for the field
 * (clear the name) from one meant for the menu (close it). */
export const NAME_FIELD_ATTR = "data-architecture-name-field";

/**
 * The header's architecture menu (021, US1, FR-001 to FR-006): the user's architectures
 * grouped by provider (AWS, GCP, Azure), each group with "New … architecture…" and Import.
 * It replaces Column 1 and keeps its actions and their accessible names: select, create,
 * make public or private, delete (with the same confirmation) and import. The data and
 * actions come from `useArchitectureLibrary`; the confirmation and Import dialogs are
 * rendered by `TopTabs`, outside the popover, so they survive it closing.
 *
 * 021 US6 (FR-041, FR-042): the providers start collapsed, as a short list. Hovering or
 * clicking one shows its group in a panel to the right of the list. From the keyboard,
 * Enter, Space or ArrowRight opens a provider's panel and moves into it; ArrowLeft goes back.
 * Each architecture can also be renamed in place (FR-043).
 */
export function ArchitectureMenu({ library }: { library: ArchitectureLibrary }) {
  const { groups } = library;
  const [openCode, setOpenCode] = useState<string | null>(null);
  const triggers = useRef(new Map<string, HTMLButtonElement>());
  const panelRef = useRef<HTMLElement>(null);
  const openGroup = groups.find((g) => g.provider.code === openCode);

  function openAndEnter(code: string) {
    setOpenCode(code);
    // After the panel renders: focus its first control.
    requestAnimationFrame(() =>
      panelRef.current?.querySelector<HTMLElement>("button:not(:disabled), input")?.focus(),
    );
  }

  return (
    <div className="flex min-h-0 flex-col gap-2">
      {library.actionError && (
        <ErrorMessage
          message={library.actionError}
          onRetry={library.dismissActionError}
          retryLabel="Dismiss"
        />
      )}
      {library.providersLoading && <p className="px-1 text-xs text-muted-foreground">Loading…</p>}
      <div className="flex min-h-0 items-stretch">
        <ul aria-label="Providers" className="flex w-36 shrink-0 flex-col gap-0.5">
          {groups.map((group) => {
            const code = asProviderCode(group.provider.code);
            const label = PROVIDER_LABELS[code] ?? group.provider.name;
            const open = openCode === group.provider.code;
            return (
              <li key={group.provider.code}>
                <button
                  type="button"
                  ref={(el) => {
                    if (el) triggers.current.set(group.provider.code, el);
                    else triggers.current.delete(group.provider.code);
                  }}
                  aria-label={label}
                  aria-expanded={open}
                  aria-controls={open ? PANEL_ID : undefined}
                  title={providerHint(group.provider)}
                  className={`flex h-8 w-full items-center justify-between gap-2 rounded-md px-2 text-sm font-medium transition-colors duration-150 hover:bg-accent active:bg-muted ${
                    open ? "bg-accent text-foreground" : "text-muted-foreground"
                  }`}
                  onPointerEnter={() => setOpenCode(group.provider.code)}
                  onClick={() => setOpenCode(group.provider.code)}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowRight" || e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      openAndEnter(group.provider.code);
                    }
                  }}
                >
                  <span>{label}</span>
                  <span className="flex items-center gap-1 text-xs text-muted-foreground">
                    <span className="tabular-nums">
                      {group.isLoading ? "" : group.architectures.length}
                    </span>
                    <ChevronRight className="size-3.5" />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        {openGroup && (
          <ProviderPanel
            ref={panelRef}
            group={openGroup}
            library={library}
            onBack={() => {
              const code = openGroup.provider.code;
              triggers.current.get(code)?.focus();
            }}
          />
        )}
      </div>
    </div>
  );
}

const PANEL_ID = "architecture-menu-provider-panel";

/** One provider's architectures, "New … architecture…" and Import, to the right of the list. */
const ProviderPanel = forwardRef<
  HTMLElement,
  { group: ProviderArchitectures; library: ArchitectureLibrary; onBack: () => void }
>(function ProviderPanel({ group, library, onBack }, ref) {
  const code = asProviderCode(group.provider.code);
  const label = PROVIDER_LABELS[code] ?? group.provider.name;
  return (
    <section
      ref={ref}
      id={PANEL_ID}
      role="group"
      aria-label={`${label} architectures`}
      className="ml-2 flex w-72 min-w-0 flex-col gap-1 border-l border-border pl-2"
      onKeyDown={(e) => {
        // ArrowLeft goes back to the provider list, except while typing in a field.
        if (e.key === "ArrowLeft" && !(e.target instanceof HTMLInputElement)) {
          e.preventDefault();
          onBack();
        }
      }}
    >
      <h3
        className="px-1 py-0.5 text-xs font-semibold text-muted-foreground"
        title={providerHint(group.provider)}
      >
        {label}
      </h3>
      {group.isLoading && <p className="px-1 text-xs text-muted-foreground">Loading…</p>}
      {group.error && <ErrorMessage message={group.error} onRetry={group.refetch} />}
      {!group.isLoading && !group.error && group.architectures.length === 0 && (
        <p className="px-1 text-xs text-muted-foreground">No architectures yet.</p>
      )}
      {group.architectures.length > 0 && (
        <ul className="flex max-h-72 flex-col gap-0.5 overflow-y-auto">
          {group.architectures.map((arch) => (
            <ArchitectureRow key={arch.id} arch={arch} library={library} />
          ))}
        </ul>
      )}
      <NewArchitectureRow
        key={code}
        providerLabel={label}
        disabled={!group.provider.active}
        disabledReason={group.provider.active ? undefined : providerHint(group.provider)}
        creating={library.creatingProvider === code}
        onCreate={(name) => library.create(code, name)}
      />
      {!library.isGuest && (
        <Button
          variant="ghost"
          size="sm"
          className="justify-start text-muted-foreground"
          disabled={!group.provider.active}
          onClick={() => library.openImport(code)}
        >
          <Download className="size-3.5" />
          {IMPORT_ARCHITECTURE_LABELS[code]}
        </Button>
      )}
    </section>
  );
});

type ArchitectureItem = ProviderArchitectures["architectures"][number];

/** An architecture: open it, make it public or private, rename it in place, or delete it. */
function ArchitectureRow({
  arch,
  library,
}: {
  arch: ArchitectureItem;
  library: ArchitectureLibrary;
}) {
  const current = arch.id === library.activeArchitectureId;
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(arch.name);
  const [saving, setSaving] = useState(false);
  const renameRef = useRef<HTMLButtonElement>(null);
  // Set when Escape cancels, so the blur that follows doesn't save.
  const cancelled = useRef(false);

  function startRename() {
    cancelled.current = false;
    setDraft(arch.name);
    setRenaming(true);
  }

  function finish() {
    setRenaming(false);
    requestAnimationFrame(() => renameRef.current?.focus());
  }

  async function commit() {
    if (cancelled.current || saving) return;
    const name = draft.trim();
    if (!name || name === arch.name) {
      finish();
      return;
    }
    setSaving(true);
    const ok = await library.rename(arch.id, name);
    setSaving(false);
    // On failure the field stays open, with the error shown above the menu.
    if (ok) finish();
  }

  return (
    <li className="flex items-start gap-0.5">
      {renaming ? (
        <input
          {...{ [NAME_FIELD_ATTR]: "" }}
          autoFocus
          onFocus={(e) => e.currentTarget.select()}
          aria-label={`Name for ${arch.name}`}
          className="h-7 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-xs"
          value={draft}
          disabled={saving}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => void commit()}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void commit();
            } else if (e.key === "Escape") {
              e.preventDefault();
              e.stopPropagation();
              cancelled.current = true;
              finish();
            }
          }}
        />
      ) : (
        <Button
          variant={current ? "secondary" : "ghost"}
          size="sm"
          aria-current={current ? "page" : undefined}
          className="h-auto min-w-0 flex-1 justify-start whitespace-normal break-words py-1 text-left"
          onClick={() => library.open(arch.id)}
        >
          {arch.name}
        </Button>
      )}
      {!library.isGuest && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={arch.is_public ? `Make ${arch.name} private` : `Make ${arch.name} public`}
              aria-pressed={arch.is_public}
              onClick={() => library.togglePublic(arch.id, !arch.is_public)}
            >
              <Users
                className={
                  arch.is_public ? "size-3.5 text-primary" : "size-3.5 text-muted-foreground"
                }
              />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {arch.is_public ? "Public: click to make private" : "Click to make public"}
          </TooltipContent>
        </Tooltip>
      )}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            ref={renameRef}
            variant="ghost"
            size="icon-sm"
            aria-label={`Rename ${arch.name}`}
            aria-pressed={renaming}
            onMouseDown={(e) => renaming && e.preventDefault()}
            onClick={() => (renaming ? void commit() : startRename())}
          >
            <Pencil className="size-3.5 text-muted-foreground" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Rename</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Delete ${arch.name}`}
            className="text-destructive hover:text-destructive"
            onClick={() => library.requestDelete(arch)}
          >
            ✕
          </Button>
        </TooltipTrigger>
        <TooltipContent>Click to remove</TooltipContent>
      </Tooltip>
    </li>
  );
}

/** "New AWS architecture…", revealing a name field and Create. Enter creates; Escape clears
 * and hides the field (the popover is told not to close for it, see `NAME_FIELD_ATTR`). */
function NewArchitectureRow({
  providerLabel,
  disabled,
  disabledReason,
  creating,
  onCreate,
}: {
  providerLabel: string;
  disabled: boolean;
  disabledReason?: string;
  creating: boolean;
  onCreate: (name: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const openerRef = useRef<HTMLButtonElement>(null);

  if (!editing) {
    return (
      <Button
        ref={openerRef}
        variant="ghost"
        size="sm"
        className="justify-start text-muted-foreground"
        disabled={disabled}
        title={disabledReason}
        onClick={() => setEditing(true)}
      >
        <Plus className="size-3.5" />
        {`New ${providerLabel} architecture…`}
      </Button>
    );
  }

  return (
    <form
      className="flex flex-wrap gap-1"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) onCreate(name.trim());
      }}
    >
      <input
        {...{ [NAME_FIELD_ATTR]: "" }}
        autoFocus
        className="h-7 min-w-[3rem] flex-1 rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            e.stopPropagation();
            setName("");
            setEditing(false);
            requestAnimationFrame(() => openerRef.current?.focus());
          }
        }}
        placeholder="Architecture name"
        aria-label={`New ${providerLabel} architecture name`}
      />
      <Button type="submit" size="sm" disabled={creating || !name.trim()}>
        Create
      </Button>
    </form>
  );
}
