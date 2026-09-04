import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PricingDataUnavailableError } from "../../src/api/client";
import { ErrorBoundary } from "../../src/components/ErrorBoundary";

function Bomb({ error }: { error: Error }): never {
  throw error;
}

describe("ErrorBoundary", () => {
  it("renders a distinct message for a pricing-data-source outage", () => {
    render(
      <ErrorBoundary>
        <Bomb error={new PricingDataUnavailableError("data source down")} />
      </ErrorBoundary>,
    );
    expect(screen.getByText(/temporarily unavailable/i)).toBeInTheDocument();
    expect(screen.getByText("data source down")).toBeInTheDocument();
  });

  it("renders a generic fallback for any other error", () => {
    render(
      <ErrorBoundary>
        <Bomb error={new Error("boom")} />
      </ErrorBoundary>,
    );
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
  });

  it("renders children when there is no error", () => {
    render(
      <ErrorBoundary>
        <p>All good</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("All good")).toBeInTheDocument();
  });
});
