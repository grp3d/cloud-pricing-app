import type { AgentProposal } from "../../src/api/client";

/** 025: a pending change proposal for "Prod Web", with two groups and one unpriced item. */
export function changeProposal(overrides: Partial<AgentProposal> = {}): AgentProposal {
  return {
    id: "p1",
    message_id: "m1",
    seq: 1,
    kind: "change",
    architecture_id: "a1",
    architecture_name: "Prod Web",
    title: "Replicate Prod Web to us-west-2",
    status: "pending",
    stale: false,
    items: [
      { ref: "P1", op: "add", target: "collection", label: "Standby (us-west-2)", group: "standby" },
      {
        ref: "P2",
        op: "add",
        target: "service",
        label: "m5.large in Standby",
        group: "standby",
        after: {},
      },
      {
        ref: "P3",
        op: "change",
        target: "service",
        label: "RDS db.m5.large in Primary",
        group: "resize",
        before: { usage_quantity: "744.0000" },
        after: { usage_quantity: "372.0000" },
      },
      { ref: "P4", op: "remove", target: "service", label: "NAT gateway in Primary", group: "resize" },
    ],
    cost: {
      duration: "1_month",
      snapshot: { provider: "aws", date: "2026-09-24", revision: 1 },
      before: { total: "1588.2249", partial: false },
      after: { total: "2310.4051", partial: true },
      difference: "722.1802",
      percent: "45.4705",
      by_service: [
        { label: "m5.large in Standby", before: null, after: "70.0800", difference: "70.0800" },
        { label: "NAT gateway in Primary", before: "33.4800", after: null, difference: "-33.4800" },
      ],
      by_region: [
        { label: "us-east-1", before: "1588.2249", after: "1554.7449", difference: "-33.48" },
        { label: "us-west-2", before: "0", after: "755.6602", difference: "755.6602" },
      ],
      contributions: [
        { group: "standby", difference: "755.6602" },
        { group: "resize", difference: "-33.48" },
      ],
      unpriceable: [{ label: "Data transfer in Primary → Standby", reason: "no price in region" }],
    },
    assumptions: [
      { kind: "region", text: "us-west-2 for the standby", guessed: true },
      { kind: "usage", text: "500 GB a month of data change", guessed: false },
    ],
    undo: null,
    created_at: "2026-11-15T12:00:00Z",
    decided_at: null,
    ...overrides,
  };
}

/** An accepted new architecture, which can be undone. */
export function acceptedCreate(overrides: Partial<AgentProposal> = {}): AgentProposal {
  return changeProposal({
    id: "p2",
    kind: "create",
    architecture_id: "a2",
    architecture_name: "Three-tier web app",
    title: "Three-tier web app on GCP",
    status: "accepted",
    items: [{ ref: "P1", op: "add", target: "collection", label: "Web (us-east1)" }],
    cost: {
      duration: "1_month",
      snapshot: { provider: "gcp", date: "2026-11-02", revision: 2 },
      after: { total: "123.4567", partial: false },
      by_service: [{ label: "e2-standard-2 in Web", after: "123.4567" }],
      by_region: [{ label: "us-east1", after: "123.4567" }],
      contributions: [],
      unpriceable: [],
    },
    assumptions: [],
    undo: { status: "available", can_undo: true, can_redo: false, end_reason: null },
    ...overrides,
  });
}
