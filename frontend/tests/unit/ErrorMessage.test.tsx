import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ErrorMessage } from "../../src/components/ErrorMessage";

describe("ErrorMessage", () => {
  it("renders the message as an alert, distinct from an empty-results state", () => {
    render(<ErrorMessage message="AWS pricing data is temporarily unavailable." />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "AWS pricing data is temporarily unavailable.",
    );
  });

  it("shows a Retry button by default when onRetry is given", () => {
    const onRetry = vi.fn();
    render(<ErrorMessage message="failed" onRetry={onRetry} />);
    fireEvent.click(screen.getByText("Retry"));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("supports a custom action label (e.g. Dismiss)", () => {
    render(<ErrorMessage message="failed" onRetry={() => {}} retryLabel="Dismiss" />);
    expect(screen.getByText("Dismiss")).toBeInTheDocument();
    expect(screen.queryByText("Retry")).not.toBeInTheDocument();
  });

  it("renders no action button when onRetry is omitted", () => {
    render(<ErrorMessage message="failed" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
