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
 */
export function AdminTabs({ tabs }: { tabs: AdminTab[] }) {
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const current = tabs.find((t) => t.id === requested)?.id ?? tabs[0].id;

  function select(id: string) {
    setParams(
      (p) => {
        const next = new URLSearchParams(p);
        next.set("tab", id);
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
    document.getElementById(`admin-tab-${tabs[target].id}`)?.focus();
  }

  return (
    <div className="flex flex-col gap-4">
      <div
        role="tablist"
        aria-label="Admin sections"
        className="flex w-fit items-center gap-0.5 rounded-lg bg-muted p-0.5"
      >
        {tabs.map((tab, index) => {
          const selected = tab.id === current;
          return (
            <button
              key={tab.id}
              id={`admin-tab-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={`admin-panel-${tab.id}`}
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
          id={`admin-panel-${tab.id}`}
          role="tabpanel"
          aria-labelledby={`admin-tab-${tab.id}`}
          hidden={tab.id !== current}
          className="flex flex-col gap-4"
        >
          {tab.content}
        </div>
      ))}
    </div>
  );
}
