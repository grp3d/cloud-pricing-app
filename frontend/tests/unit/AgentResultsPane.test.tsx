import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AgentResultCard } from "../../src/components/agent/AgentResultCard";
import { AgentResultsPane } from "../../src/components/agent/AgentResultsPane";
import { TooltipProvider } from "../../src/components/ui/tooltip";
import { architectureResult } from "./agentResultFixture";

/** 024 US6 (contracts/results-pane-ui.md "Results pane content"). */

function renderPane(props: Partial<Parameters<typeof AgentResultsPane>[0]> = {}) {
  const results = props.results ?? [
    architectureResult(),
    architectureResult({ id: "r2", seq: 2, title: "Second" }),
  ];
  const handlers = { onStep: vi.fn(), onClose: vi.fn(), download: vi.fn(async () => {}) };
  render(
    <TooltipProvider>
      <AgentResultsPane results={results} selectedId="r1" {...handlers} {...props} />
    </TooltipProvider>,
  );
  return handlers;
}

describe("AgentResultsPane", () => {
  it("has the header controls with names, and steps", () => {
    const { onStep, onClose } = renderPane();
    expect(screen.getByText("Result 1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous result" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Next result" }));
    expect(onStep).toHaveBeenCalledWith(1);
    fireEvent.click(screen.getByRole("button", { name: "Close results" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("states the basis, with guessed regions", () => {
    renderPane();
    expect(screen.getByText(/Azure: eastus \(guessed\) · on demand · prices from 2026-11-03/))
      .toBeInTheDocument();
    expect(screen.getByText(/AWS: us-east-1 · as in the architecture/)).toBeInTheDocument();
    expect(screen.getByText(/1 month \(31 days\) · USD · as in the architecture/))
      .toBeInTheDocument();
    expect(screen.getByText(/Assumptions: Azure on demand/)).toBeInTheDocument();
  });

  it("draws the table from the result, rounded like the CSV", () => {
    renderPane();
    const table = screen.getByRole("table", { name: "Three-tier web app: AWS vs Azure" });
    const database = within(table).getByRole("row", { name: /Database/ });
    expect(within(database).getByText("$380.12")).toBeInTheDocument();
    expect(within(database).getByText("$468.01")).toBeInTheDocument();
    expect(within(database).getByText("+$87.88")).toBeInTheDocument();
    expect(within(database).getByText("+23.1%")).toBeInTheDocument();
    expect(within(database).getByRole("button", { name: "Close match: x86 vs arm" }))
      .toBeInTheDocument();
  });

  it("shows no number for a cell without a price", () => {
    renderPane();
    const queue = screen.getByRole("row", { name: /Queue/ });
    expect(
      within(queue).getByRole("button", {
        name: "No equivalent: no product in the same category",
      }),
    ).toBeInTheDocument();
    expect(within(queue).queryByText(/\$0\.00/)).toBeNull();
  });

  it("labels a partial total and lists what wasn't compared", () => {
    renderPane();
    expect(screen.getByRole("rowheader", { name: "Total (partial)" })).toBeInTheDocument();
    expect(screen.getByText("Not compared:")).toBeInTheDocument();
    expect(screen.getByText("Queue (AZURE: no product in the same category)"))
      .toBeInTheDocument();
  });

  it("downloads the shown result, and says so when that fails", async () => {
    const download = vi.fn().mockRejectedValueOnce(new Error("no")).mockResolvedValue(undefined);
    renderPane({ download });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Download CSV/ }));
    });
    expect(download).toHaveBeenCalledWith("r1");
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't download the result.");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Download CSV/ }));
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("AgentResultCard", () => {
  it("names the result, marks the one shown, and shows it", () => {
    const onShow = vi.fn();
    render(<AgentResultCard result={architectureResult()} current onShow={onShow} />);
    const card = screen.getByRole("button", {
      name: "Show result: Three-tier web app: AWS vs Azure",
    });
    expect(card).toHaveAttribute("aria-current", "true");
    expect(card).toHaveTextContent("2 rows · Azure total +23.1% (partial)");
    fireEvent.click(card);
    expect(onShow).toHaveBeenCalledWith("r1");
  });
});
