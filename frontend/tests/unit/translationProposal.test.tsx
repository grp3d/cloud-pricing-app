import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiStatusError, api } from "../../src/api/client";
import { AgentProposalView } from "../../src/components/agent/AgentProposalView";
import {
  actionErrorText,
  cardSummary,
  isStaleRefusal,
  statusOf,
} from "../../src/lib/agentProposals";
import { translationProposal } from "./agentProposalFixture";

/** 026 (contracts/translation-ui.md, FR-012): a translation in the view and on its card. */

afterEach(() => vi.restoreAllMocks());

function renderView(proposal = translationProposal()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AgentProposalView
        proposal={proposal}
        position={{ index: 0, total: 1 }}
        openArchitectureId={null}
        answering={false}
        onStep={vi.fn()}
        onClose={vi.fn()}
        onOpenArchitecture={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

const STALE = new ApiStatusError(
  409,
  {
    error: "stale_translation",
    message:
      "The original or the pricing data changed since this translation. Ask me to translate it again.",
  },
  "stale",
);

describe("translation card text", () => {
  it("names the translation and the difference on matched services", () => {
    expect(cardSummary(translationProposal())).toBe(
      "Prod Web → Azure · on 3 matched services -$52.72 (-17.6%) · 1 left out",
    );
  });

  it("a stale translation refusal is its message, not a re-pricing", () => {
    expect(isStaleRefusal(STALE)).toBe(false);
    expect(actionErrorText(STALE)).toMatch(/Ask me to translate it again/);
  });
});

describe("translation view", () => {
  it("shows the new architecture, the mapping table and the cost difference", () => {
    renderView();
    expect(screen.getByText("New architecture on Azure: Prod Web")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Mapping" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Cost difference" })).toBeInTheDocument();
    expect(screen.queryByText("By region")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept" })).toBeEnabled();
  });

  it("a stale translation can't be accepted and says what to do", () => {
    const proposal = translationProposal({ stale: true });
    expect(statusOf(proposal)).toBe("stale");
    renderView(proposal);
    expect(
      screen.getByText(
        "The original or the pricing data changed. Ask the agent to translate it again.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept" })).not.toBeInTheDocument();
  });

  it("an accept refused as stale shows the reason", async () => {
    vi.spyOn(api, "acceptProposal").mockRejectedValueOnce(STALE);
    renderView();
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ask me to translate it again.");
  });
});
