import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiStatusError, api } from "../../src/api/client";
import { AgentProposalCard } from "../../src/components/agent/AgentProposalCard";
import { AgentProposalView } from "../../src/components/agent/AgentProposalView";
import { acceptedCreate, changeProposal } from "./agentProposalFixture";

/** 025 (contracts/proposal-ui.md): the proposal view and card. */

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

function renderView(props: Partial<Parameters<typeof AgentProposalView>[0]> = {}) {
  const handlers = { onStep: vi.fn(), onClose: vi.fn(), onOpenArchitecture: vi.fn() };
  wrap(
    <AgentProposalView
      proposal={changeProposal()}
      position={{ index: 0, total: 2 }}
      openArchitectureId="a1"
      answering={false}
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

afterEach(() => vi.restoreAllMocks());

describe("AgentProposalView", () => {
  it("has the pane's header controls", () => {
    const { onStep, onClose } = renderView();
    expect(screen.getByText("Result 1 of 2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next result" }));
    expect(onStep).toHaveBeenCalledWith(1);
    fireEvent.click(screen.getByRole("button", { name: "Close results" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("lists the changes grouped as added, changed and removed", () => {
    renderView();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("Added")).toBeInTheDocument();
    expect(screen.getByText("Standby (us-west-2)")).toBeInTheDocument();
    expect(screen.getByText("Changed")).toBeInTheDocument();
    expect(screen.getByText("quantity 744.0000 → 372.0000")).toBeInTheDocument();
    expect(screen.getByText("Removed")).toBeInTheDocument();
  });

  it("shows the engine's cost before and after, rounded, with a partial total", () => {
    renderView();
    const table = screen.getByRole("table", { name: "Cost" });
    const total = within(table).getByRole("row", { name: /Total \(partial\)/ });
    expect(within(total).getByText("$1,588.22")).toBeInTheDocument();
    expect(within(total).getByText("$2,310.41")).toBeInTheDocument();
    expect(within(total).getByText("+$722.18")).toBeInTheDocument();
    expect(within(total).getByText("+45.5%")).toBeInTheDocument();
    expect(screen.getByText("Not priced")).toBeInTheDocument();
    expect(screen.getByText(/Data transfer in Primary → Standby: no price in region/))
      .toBeInTheDocument();
    expect(screen.getByText(/1 month \(31 days\) · USD · prices from 2026-09-24/))
      .toBeInTheDocument();
  });

  it("shows each change's share in order, and the assumptions with guesses", () => {
    renderView();
    expect(screen.getByText("Each change's share, in order")).toBeInTheDocument();
    expect(screen.getByText("+$755.66")).toBeInTheDocument();
    expect(screen.getByText("us-west-2 for the standby (guess)")).toBeInTheDocument();
    expect(screen.getByText("500 GB a month of data change")).toBeInTheDocument();
  });

  it("accepts with the open architecture", async () => {
    const accept = vi.spyOn(api, "acceptProposal").mockResolvedValue({
      proposal: changeProposal({ status: "accepted" }),
      open_architecture_id: null,
    });
    renderView();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    });
    expect(accept).toHaveBeenCalledWith("p1", "a1", false);
  });

  it("can't accept a change while its architecture isn't open, or while answering", () => {
    renderView({ openArchitectureId: "other" });
    expect(screen.getByText("Open Prod Web to accept this change.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept" })).toBeDisabled();
  });

  it("waits while a message is answered", () => {
    renderView({ answering: true });
    expect(screen.getByText("Wait until the agent has finished answering.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
  });

  it("says a proposal is stale, and asks again with the updated figures", async () => {
    const accept = vi
      .spyOn(api, "acceptProposal")
      .mockRejectedValueOnce(new ApiStatusError(409, { error: "stale" }, "stale"))
      .mockResolvedValue({ proposal: changeProposal(), open_architecture_id: null });
    renderView({ proposal: changeProposal({ stale: true }) });
    expect(screen.getByText("Stale")).toBeInTheDocument();
    expect(screen.getByText(/Prod Web changed after this proposal was made/)).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    });
    expect(screen.getByRole("button", { name: "Accept updated proposal" })).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Accept updated proposal" }));
    });
    expect(accept).toHaveBeenLastCalledWith("p1", "a1", true);
  });

  it("shows a refusal briefly", async () => {
    vi.spyOn(api, "rejectProposal").mockRejectedValue(
      new ApiStatusError(409, "This proposal isn't waiting for a decision.", "x"),
    );
    renderView();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "This proposal isn't waiting for a decision.",
    );
  });

  it("opens a new architecture after accepting it", async () => {
    vi.spyOn(api, "acceptProposal").mockResolvedValue({
      proposal: acceptedCreate(),
      open_architecture_id: "a2",
    });
    const { onOpenArchitecture } = renderView({
      proposal: acceptedCreate({ status: "pending", undo: null }),
      openArchitectureId: null,
    });
    expect(screen.getByText("New architecture: Three-tier web app")).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Before" })).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    });
    expect(onOpenArchitecture).toHaveBeenCalledWith("a2");
  });

  it("says a superseded proposal was replaced, with no actions", () => {
    renderView({ proposal: changeProposal({ status: "superseded" }) });
    expect(screen.getByText("Superseded")).toBeInTheDocument();
    expect(screen.getByText(/A newer proposal replaced this one/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
  });

  it("offers Undo when accepted, and says why when undo has ended", () => {
    renderView({ proposal: acceptedCreate() });
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
  });

  it("explains an ended undo", () => {
    renderView({
      proposal: acceptedCreate({
        undo: { status: "ended", can_undo: false, can_redo: false, end_reason: "edited" },
      }),
    });
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
    expect(
      screen.getByText("Your latest edit means the agent's previous change can no longer be undone."),
    ).toBeInTheDocument();
  });
});

describe("AgentProposalCard", () => {
  it("names the proposal with its changes and cost difference, and shows it", () => {
    const onShow = vi.fn();
    wrap(<AgentProposalCard proposal={changeProposal()} current={false} onShow={onShow} />);
    expect(screen.getByText("Prod Web · 4 changes · +$722.18 (+45.5%)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Show proposal/ }));
    expect(onShow).toHaveBeenCalledWith("p1");
  });

  it("gives a new architecture's total, and Undo once accepted", async () => {
    const undo = vi.spyOn(api, "undoProposal").mockResolvedValue({
      proposal: acceptedCreate(),
      open_architecture_id: null,
    });
    wrap(<AgentProposalCard proposal={acceptedCreate()} current onShow={vi.fn()} />);
    expect(screen.getByText("New: Three-tier web app · 1 change · $123.46")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    });
    expect(undo).toHaveBeenCalledWith("p2");
  });

  it("shows Redo after an undo, and the reason once undo has ended", () => {
    const { unmount } = wrap(
      <AgentProposalCard
        proposal={acceptedCreate({
          undo: { status: "undone", can_undo: false, can_redo: true, end_reason: null },
        })}
        current={false}
        onShow={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Redo" })).toBeInTheDocument();
    expect(screen.getByText(/· Undone/)).toBeInTheDocument();
    unmount();
    wrap(
      <AgentProposalCard
        proposal={acceptedCreate({
          undo: { status: "ended", can_undo: false, can_redo: false, end_reason: "superseded" },
        })}
        current={false}
        onShow={vi.fn()}
      />,
    );
    expect(screen.getByText(/A later change replaced this one/)).toBeInTheDocument();
  });
});
