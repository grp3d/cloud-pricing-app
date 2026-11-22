import type { ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

export interface AdminTab {
  id: string;
  label: string;
  content: ReactNode;
}

/**
 * 023: the Admin page's tabs, styled like the inspector's Pricing/Service tabs. The open tab is
 * kept in the address (`?tab=users`), so a reload or a shared link opens the same one. Every
 * panel stays mounted while hidden, so unsaved edits survive switching tabs.
 *
 * 027 (US6): also System Information's Providers and Issues tabs, with their own address
 * parameter (`?section=issues`), list label and ids, so the two sets of tabs don't collide.
 */
export function AdminTabs({
  tabs,
  param = "tab",
  label = "Admin sections",
  idPrefix = "admin",
}: {
  tabs: AdminTab[];
  param?: string;
  label?: string;
  idPrefix?: string;
}) {
  const [params, setParams] = useSearchParams();
  const requested = params.get(param);
  const current = tabs.find((t) => t.id === requested)?.id ?? tabs[0].id;

  function select(id: string) {
    setParams(
      (p) => {
        const next = new URLSearchParams(p);
        next.set(param, id);
        return next;
      },
      { replace: true },
    );
  }

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    const last = tabs.length - 1;
    const target =
      e.key === "ArrowRight"
        ? (index + 1) % tabs.length
        : e.key === "ArrowLeft"
          ? (index - 1 + tabs.length) % tabs.length
          : e.key === "Home"
            ? 0
            : e.key === "End"
              ? last
              : null;
    if (target === null) return;
    e.preventDefault();
    select(tabs[target].id);
    document.getElementById(`${idPrefix}-tab-${tabs[target].id}`)?.focus();
  }

  return (
    <div className="flex flex-col gap-4">
      <div
        role="tablist"
        aria-label={label}
        className="flex w-fit items-center gap-0.5 rounded-lg bg-muted p-0.5"
      >
        {tabs.map((tab, index) => {
          const selected = tab.id === current;
          return (
            <button
              key={tab.id}
              id={`${idPrefix}-tab-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={`${idPrefix}-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              className={`focus-ring h-7 rounded-md px-2.5 text-xs font-medium transition-colors ${
                selected
                  ? "bg-background text-foreground shadow-xs"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              }`}
              onClick={() => select(tab.id)}
              onKeyDown={(e) => onKeyDown(e, index)}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          id={`${idPrefix}-panel-${tab.id}`}
          role="tabpanel"
          aria-labelledby={`${idPrefix}-tab-${tab.id}`}
          hidden={tab.id !== current}
          className="flex flex-col gap-4"
        >
          {tab.content}
        </div>
      ))}
    </div>
  );
}
