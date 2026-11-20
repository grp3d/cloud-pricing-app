import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TranslationTable } from "../../src/components/agent/TranslationTable";
import { translationProposal } from "./agentProposalFixture";

/** 026 (contracts/translation-ui.md): the mapping table and the cost difference. */

function renderTable() {
  const proposal = translationProposal();
  render(<TranslationTable translation={proposal.translation!} />);
}

describe("TranslationTable", () => {
  it("states the regions, guesses and the term", () => {
    renderTable();
    expect(screen.getByText("us-east-1 → eastus (a guess)")).toBeInTheDocument();
    expect(
      screen.getByText(/Pricing: on demand — the original uses reserved 1 year/),
    ).toBeInTheDocument();
  });

  it("has one row per source service with match, quality, origin and both costs", () => {
    renderTable();
    const table = screen.getByRole("table", { name: "Mapping" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(4);
    const vm = within(rows[0]);
    expect(vm.getByText("EC2 t4g.xlarge")).toBeInTheDocument();
    expect(vm.getByText("D4s v5")).toBeInTheDocument();
    expect(vm.getByText("Close")).toBeInTheDocument();
    expect(vm.getByText("Seeded")).toBeInTheDocument();
    expect(vm.getByText("x86_64 vs arm64")).toBeInTheDocument();
    expect(vm.getByText("$250.12")).toBeInTheDocument();
    expect(vm.getByText("$200.50")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Automatic")).toBeInTheDocument();
    expect(within(rows[1]).getByText("1 other option")).toBeInTheDocument();
    const chosen = within(rows[2]);
    expect(chosen.getByText("Chosen by you")).toBeInTheDocument();
    expect(
      chosen.getByText("Partial match you chose; not checked as equivalent."),
    ).toBeInTheDocument();
  });

  it("shows a left-out row with its reason and no match cost", () => {
    renderTable();
    const rows = within(screen.getByRole("table", { name: "Mapping" })).getAllByRole("row");
    const left = within(rows[4]);
    expect(
      left.getByText("No equivalent: Azure Load Balancer has no LCU-hour unit"),
    ).toBeInTheDocument();
    expect(left.getAllByText("—")).toHaveLength(1);
  });

  it("gives both totals, the difference on matched services, drivers and snapshots", () => {
    renderTable();
    const cost = screen.getByRole("region", { name: "Cost difference" });
    const c = within(cost);
    expect(c.getByText("AWS total")).toBeInTheDocument();
    expect(c.getByText("$304.32")).toBeInTheDocument();
    expect(c.getByText("Azure total (partial)")).toBeInTheDocument();
    expect(c.getByText("$247.30")).toBeInTheDocument();
    expect(c.getByText("On the 3 matched services: -$52.72 (-17.6%)")).toBeInTheDocument();
    expect(
      c.getByText("ALB LCU in Web: Azure Load Balancer has no LCU-hour unit"),
    ).toBeInTheDocument();
    expect(c.getByText("EC2 t4g.xlarge (Web)")).toBeInTheDocument();
    expect(c.getByText("-$49.62")).toBeInTheDocument();
    expect(
      c.getByText(/1 month \(31 days\) · USD · prices from AWS 2026-09-24, Azure 2026-11-02/),
    ).toBeInTheDocument();
  });
});
