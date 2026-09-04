import { Component, type ErrorInfo, type ReactNode } from "react";

import { PricingDataUnavailableError } from "../api/client";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Top-level error boundary. A `PricingDataUnavailableError` (HTTP 503 — spec FR-018) renders a
 * distinct "data source unavailable, retry" state; every other error gets a generic fallback.
 * Never conflated with an empty/"no results" state, which components render themselves.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled error", error, info);
  }

  private reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    if (error instanceof PricingDataUnavailableError) {
      return (
        <div role="alert" style={{ padding: 24 }}>
          <h2>AWS pricing data is temporarily unavailable</h2>
          <p>{error.message}</p>
          <button onClick={this.reset}>Retry</button>
        </div>
      );
    }

    return (
      <div role="alert" style={{ padding: 24 }}>
        <h2>Something went wrong</h2>
        <p>{error.message}</p>
        <button onClick={this.reset}>Retry</button>
      </div>
    );
  }
}
