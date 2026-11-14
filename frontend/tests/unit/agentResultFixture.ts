/** 024: a comparison result for the Results pane tests. */
import type { AgentResult } from "../../src/api/client";

export function architectureResult(overrides: Partial<AgentResult> = {}): AgentResult {
  return {
    id: "r1",
    message_id: "m1",
    seq: 1,
    kind: "architecture_comparison",
    title: "Three-tier web app: AWS vs Azure",
    summary: "2 rows · Azure total +23.1% (partial)",
    created_at: "2026-11-13T12:00:00Z",
    basis: {
      question_kind: "architecture",
      architecture: "Three-tier web app",
      category: null,
      duration: "1_month",
      currency: "USD",
      reference_side: "aws",
      usage: "as in the architecture",
      assumptions: ["Azure on demand (default term)"],
    },
    sides: [
      { id: "aws", provider: "aws", region: "us-east-1", region_guessed: false, term: "as_saved" },
      { id: "azure", provider: "azure", region: "eastus", region_guessed: true, term: "on_demand" },
    ],
    rows: [
      {
        label: "Database",
        where: "App tier",
        cells: {
          aws: { product: "RDS db.r6g.xlarge", amount: "380.1234", status: "ok" },
          azure: {
            product: "PostgreSQL E4ds_v5",
            quality: "close",
            shown_quality: "close",
            differences: ["x86 vs arm"],
            amount: "468.005",
            diff: "87.8816",
            diff_pct: "23.12",
            status: "ok",
          },
        },
      },
      {
        label: "Queue",
        where: "App tier",
        cells: {
          aws: { product: "SQS", amount: "12", status: "ok" },
          azure: { status: "unmatched", reason: "no product in the same category" },
        },
      },
    ],
    totals: {
      aws: { amount: "380.1234", partial: true },
      azure: { amount: "468.005", partial: true, diff: "87.8816", diff_pct: "23.12" },
    },
    snapshots: { aws: { date: "2026-11-02", revision: 2 }, azure: { date: "2026-11-03", revision: 1 } },
    not_compared: ["Queue (AZURE: no product in the same category)"],
    ...overrides,
  } as AgentResult;
}
