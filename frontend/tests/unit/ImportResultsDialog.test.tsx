import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ImportResultsDialog } from "../../src/components/ImportResultsDialog";

const noop = () => {};

describe("ImportResultsDialog", () => {
  it("renders one row per result with Status, Architecture and Error columns (FR-022)", () => {
    render(
      <ImportResultsDialog
        open
        onOpenChange={noop}
        results={[
          { name: "Web App", status: "success", error: null },
          { name: "Data Lake", status: "failed", error: "Architecture name already exists" },
        ]}
      />,
    );
    const table = screen.getByRole("table");
    expect(within(table).getByText("Status")).toBeInTheDocument();
    expect(within(table).getByText("Architecture")).toBeInTheDocument();
    expect(within(table).getByText("Error")).toBeInTheDocument();

    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);

    expect(within(rows[0]).getByLabelText("Imported")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Web App")).toBeInTheDocument();
    expect(rows[0].querySelectorAll("td")[2]).toHaveTextContent("");

    expect(within(rows[1]).getByLabelText("Failed")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Architecture name already exists")).toBeInTheDocument();
  });

  it("colors success green and failure red", () => {
    render(
      <ImportResultsDialog
        open
        onOpenChange={noop}
        results={[
          { name: "A", status: "success", error: null },
          { name: "B", status: "failed", error: "nope" },
        ]}
      />,
    );
    expect(screen.getByLabelText("Imported")).toHaveClass("text-green-600");
    expect(screen.getByLabelText("Failed")).toHaveClass("text-destructive");
  });

  it("labels an entry with no readable name by its position", () => {
    render(
      <ImportResultsDialog
        open
        onOpenChange={noop}
        results={[
          { name: "First", status: "success", error: null },
          { name: null, status: "failed", error: "Invalid architecture definition: name Field required" },
        ]}
      />,
    );
    expect(screen.getByText("(unnamed #2)")).toBeInTheDocument();
  });

  it("says so when the file held no architectures", () => {
    render(<ImportResultsDialog open onOpenChange={noop} results={[]} />);
    expect(screen.getByText("No architectures were found in this file.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows a whole-file failure message instead of a table (FR-019)", () => {
    render(
      <ImportResultsDialog
        open
        onOpenChange={noop}
        results={[]}
        failedMessage="Import failed: the file is not valid JSON."
      />,
    );
    expect(screen.getByText("Import failed: the file is not valid JSON.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
