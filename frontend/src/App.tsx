import { Route, Routes } from "react-router-dom";

import { ErrorBoundary } from "./components/ErrorBoundary";
import { TooltipProvider } from "./components/ui/tooltip";
import { WorkspacePage } from "./pages/WorkspacePage";

/**
 * Both routes render the same `WorkspacePage` shell (007-ui-overhaul-shadcn, research.md §4)
 * — selecting an Architecture updates the URL via `navigate()` without unmounting/reloading
 * this tree, so Architectures stay individually bookmarkable with no page-reload transition.
 */
export function App() {
  return (
    <ErrorBoundary>
      <TooltipProvider>
        <Routes>
          <Route path="/" element={<WorkspacePage />} />
          <Route path="/architectures/:architectureId" element={<WorkspacePage />} />
        </Routes>
      </TooltipProvider>
    </ErrorBoundary>
  );
}
