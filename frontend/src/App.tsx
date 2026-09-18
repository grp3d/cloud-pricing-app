import { Route, Routes, useLocation } from "react-router-dom";

import { ErrorBoundary } from "./components/ErrorBoundary";
import { PermissionDeniedProvider } from "./components/layout/PermissionDeniedDialog";
import { RequireAdmin, useTrackLastNonAdminPath } from "./components/layout/RequireAdmin";
import { TopTabs } from "./components/layout/TopTabs";
import { TooltipProvider } from "./components/ui/tooltip";
import { AdminPage } from "./pages/AdminPage";
import { WorkspacePage } from "./pages/WorkspacePage";

/**
 * `/` and `/architectures/:id` both render the same `WorkspacePage` shell
 * (007-ui-overhaul-shadcn, research.md §4) — selecting an Architecture updates the URL via
 * `navigate()` without unmounting/reloading this tree, so Architectures stay individually
 * bookmarkable with no page-reload transition. `TopTabs` (012-user-accounts-sharing) is new
 * chrome above that tree — the tab bar and person icon that stay visible regardless of which
 * tab is active; `/admin` is gated by `RequireAdmin` (follow-up fix), since a disappearing
 * tab-bar link alone doesn't unmount an already-routed page when a session's admin status
 * changes.
 */
export function App() {
  const location = useLocation();
  useTrackLastNonAdminPath(location.pathname);

  return (
    <ErrorBoundary>
      <TooltipProvider>
        <PermissionDeniedProvider>
          <div className="flex h-screen w-screen flex-col overflow-hidden">
            <TopTabs />
            <div className="min-h-0 flex-1">
              <Routes>
                <Route path="/" element={<WorkspacePage />} />
                <Route path="/architectures/:architectureId" element={<WorkspacePage />} />
                <Route
                  path="/admin"
                  element={
                    <RequireAdmin>
                      <AdminPage />
                    </RequireAdmin>
                  }
                />
              </Routes>
            </div>
          </div>
        </PermissionDeniedProvider>
      </TooltipProvider>
    </ErrorBoundary>
  );
}
