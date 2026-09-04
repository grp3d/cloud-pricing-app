import { Route, Routes } from "react-router-dom";

import { ErrorBoundary } from "./components/ErrorBoundary";
import { CreateArchitecturePage } from "./pages/CreateArchitecturePage";
import { LandingPage } from "./pages/LandingPage";

export function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/architectures/:architectureId" element={<CreateArchitecturePage />} />
      </Routes>
    </ErrorBoundary>
  );
}
