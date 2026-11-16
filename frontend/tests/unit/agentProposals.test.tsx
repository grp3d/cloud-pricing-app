import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../../src/api/client";
import { AgentActivityLog } from "../../src/components/agent/AgentActivityLog";
import {
  changeText,
  groupItems,
  statusOf,
  undoEnds,
  undoJustEndedByEdit,
} from "../../src/lib/agentProposals";
import { acceptedCreate, changeProposal } from "./agentProposalFixture";

/** 025 (FR-006, FR-014, contracts/proposal-ui.md). */

afterEach(() => vi.restoreAllMocks());

describe("proposal helpers", () => {
  it("names the status, including stale and undone", () => {
    expect(statusOf(changeProposal())).toBe("pending");
    expect(statusOf(changeProposal({ stale: true }))).toBe("stale");
    expect(
      statusOf(
        acceptedCreate({
          undo: { status: "undone", can_undo: false, can_redo: true, end_reason: null },
        }),
      ),
    ).toBe("undone");
  });

  it("groups items and describes a change", () => {
    const groups = groupItems(changeProposal().items);
    expect([groups.add.length, groups.change.length, groups.remove.length]).toEqual([2, 1, 1]);
    expect(changeText(groups.change[0])).toBe("quantity 744.0000 → 372.0000");
  });

  it("notices once when an edit ends undo, not on the first load", () => {
    const open = acceptedCreate();
    const ended = acceptedCreate({
      undo: { status: "ended", can_undo: false, can_redo: false, end_reason: "edited" },
    });
    expect(undoJustEndedByEdit({}, undoEnds([ended]))).toBe(false); // already ended when loaded
    expect(undoJustEndedByEdit(undoEnds([open]), undoEnds([ended]))).toBe(true);
    expect(undoJustEndedByEdit(undoEnds([ended]), undoEnds([ended]))).toBe(false); // once
    const superseded = acceptedCreate({
      undo: { status: "ended", can_undo: false, can_redo: false, end_reason: "superseded" },
    });
    expect(undoJustEndedByEdit(undoEnds([open]), undoEnds([superseded]))).toBe(false);
  });
});

describe("AgentActivityLog", () => {
  it("names the user's decisions as theirs", async () => {
    vi.spyOn(api, "getAgentOperations").mockResolvedValue([
      {
        message_id: "m1",
        name: "propose_changes",
        inputs: {},
        outcome: "ok",
        summary: {},
        snapshot: null,
        figures_removed: 0,
        started_at: "2026-11-15T12:00:00Z",
        duration_ms: 12,
      },
      {
        message_id: "m1",
        name: "accept_proposal",
        inputs: { proposal_id: "p1" },
        outcome: "ok",
        summary: { title: "Replicate", items: 4 },
        snapshot: null,
        figures_removed: 0,
        started_at: "2026-11-15T12:01:00Z",
        duration_ms: 0,
      },
    ]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <AgentActivityLog />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("You accepted a proposal")).toBeInTheDocument();
    expect(screen.getByText("propose_changes")).toBeInTheDocument();
  });
});
