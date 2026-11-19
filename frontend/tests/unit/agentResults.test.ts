import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CLOSED,
  downloadResultCsv,
  formatMoney,
  formatPercent,
  readResultsSplit,
  resultsPane,
  roundDecimal,
  writeResultsSplit,
} from "../../src/lib/agentResults";

/** 024 US6 (contracts/results-pane-ui.md, FR-018–FR-020). */

describe("resultsPane", () => {
  const ids = ["r1", "r2", "r3"];

  it("is hidden with no results and opens on the latest when a session is reopened", () => {
    expect(resultsPane(CLOSED, { type: "loaded", ids: [] })).toEqual(CLOSED);
    expect(resultsPane(CLOSED, { type: "loaded", ids })).toEqual({ open: true, selectedId: "r3" });
  });

  it("keeps the shown result when the session reloads", () => {
    const shown = { open: true, selectedId: "r1" };
    expect(resultsPane(shown, { type: "loaded", ids })).toBe(shown);
  });

  it("opens on a new result, closes, and a card shows its result again", () => {
    let state = resultsPane(CLOSED, { type: "arrived", id: "r1" });
    expect(state).toEqual({ open: true, selectedId: "r1" });
    state = resultsPane(state, { type: "close" });
    expect(state.open).toBe(false);
    state = resultsPane(state, { type: "show", id: "r2" });
    expect(state).toEqual({ open: true, selectedId: "r2" });
  });

  it("steps through results and stops at the ends", () => {
    let state = { open: true, selectedId: "r2" };
    state = resultsPane(state, { type: "step", delta: 1, ids });
    expect(state.selectedId).toBe("r3");
    expect(resultsPane(state, { type: "step", delta: 1, ids })).toBe(state);
    const first = { open: true, selectedId: "r1" };
    expect(resultsPane(first, { type: "step", delta: -1, ids })).toBe(first);
  });

  it("resets for a new session", () => {
    expect(resultsPane({ open: true, selectedId: "r2" }, { type: "reset" })).toEqual(CLOSED);
  });
});

describe("figures", () => {
  it.each([
    ["468.005", "468.01"],
    ["380.1234", "380.12"],
    ["1780.955", "1780.96"],
    ["-2061.555", "-2061.56"],
    ["9.995", "10.00"],
    ["0.004", "0.00"],
    ["-0.004", "0.00"],
    ["12", "12.00"],
  ])("rounds %s half-up on its decimal digits to %s", (value, rounded) => {
    expect(roundDecimal(value, 2)).toBe(rounded);
  });

  it("formats money and percentages like the answer text", () => {
    expect(formatMoney("1234567.891")).toBe("$1,234,567.89");
    expect(formatMoney("-12")).toBe("-$12.00");
    expect(formatMoney(null)).toBe("");
    // An unchanged service's zero difference, in Python's exponent form (T065, 2026-11-19).
    expect(formatMoney("0E-13")).toBe("$0.00");
    expect(formatMoney("-1.2345E+3")).toBe("-$1,234.50");
    expect(formatMoney("5E-3")).toBe("$0.01");
    expect(formatPercent("12.35")).toBe("+12.4%");
    expect(formatPercent("-4")).toBe("-4.0%");
    expect(formatPercent("0.01")).toBe("0.0%");
  });
});

describe("the results split", () => {
  it("reads the saved split, clamped, with a default", () => {
    expect(readResultsSplit(null)).toBe(0.45);
    expect(readResultsSplit({ agent_results: { split: 0.6 } })).toBe(0.6);
    expect(readResultsSplit({ agent_results: { split: 0.9 } })).toBe(0.75);
  });

  it("saves the split with the rest of the workspace", () => {
    const store = {
      current: { workspace: { last_provider: "aws" } },
      patchSection: vi.fn(),
    };
    writeResultsSplit(0.523, store as never);
    expect(store.patchSection).toHaveBeenCalledWith("workspace", {
      last_provider: "aws",
      agent_results: { split: 0.52 },
    });
  });
});

describe("downloadResultCsv", () => {
  afterEach(() => vi.restoreAllMocks());

  it("fetches with the auth header and saves with the server's filename", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("﻿Comparison,x\r\n", {
        status: 200,
        headers: {
          "Content-Disposition": 'attachment; filename="comparison-x-2026-11-13.csv"',
        },
      }),
    );
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    const clicked: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked.push(this.download);
    });
    await downloadResultCsv("r1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/agent\/session\/results\/r1\/csv$/);
    expect((init?.headers as Record<string, string>).Authorization).toMatch(/^Bearer /);
    expect(clicked).toEqual(["comparison-x-2026-11-13.csv"]);
  });

  it("throws when the download fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 404 }));
    await expect(downloadResultCsv("r1")).rejects.toThrow("download failed");
  });
});
