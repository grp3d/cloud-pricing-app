import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AdminTabs } from "../../src/components/admin/AdminTabs";

function Draft() {
  const [value, setValue] = useState("");
  return <input aria-label="Draft" value={value} onChange={(e) => setValue(e.target.value)} />;
}

function Search() {
  return <p data-testid="search">{useLocation().search}</p>;
}

function renderTabs(entry = "/admin") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <AdminTabs
        tabs={[
          { id: "agent", label: "Agent Settings", content: <Draft /> },
          { id: "users", label: "User Management", content: <p>Users table</p> },
          { id: "system", label: "System Information", content: <p>System panel</p> },
        ]}
      />
      <Search />
    </MemoryRouter>,
  );
}

const tab = (name: string) => screen.getByRole("tab", { name });

describe("AdminTabs", () => {
  it("opens the first tab by default and shows only its panel", () => {
    renderTabs();
    expect(tab("Agent Settings")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Agent Settings" })).toBeVisible();
    expect(screen.getByText("Users table")).not.toBeVisible();
  });

  it("switches tabs on click and keeps the tab in the address", () => {
    renderTabs();
    fireEvent.click(tab("User Management"));
    expect(tab("User Management")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Users table")).toBeVisible();
    expect(screen.getByTestId("search")).toHaveTextContent("?tab=users");
  });

  it("opens the tab named in the address", () => {
    renderTabs("/admin?tab=system");
    expect(screen.getByText("System panel")).toBeVisible();
  });

  it("falls back to the first tab for an unknown name", () => {
    renderTabs("/admin?tab=nope");
    expect(tab("Agent Settings")).toHaveAttribute("aria-selected", "true");
  });

  it("moves between tabs with the arrow keys, Home and End", () => {
    renderTabs();
    fireEvent.keyDown(tab("Agent Settings"), { key: "ArrowRight" });
    expect(tab("User Management")).toHaveAttribute("aria-selected", "true");
    expect(tab("User Management")).toHaveFocus();
    fireEvent.keyDown(tab("User Management"), { key: "End" });
    expect(tab("System Information")).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tab("System Information"), { key: "ArrowRight" });
    expect(tab("Agent Settings")).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tab("Agent Settings"), { key: "ArrowLeft" });
    expect(tab("System Information")).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tab("System Information"), { key: "Home" });
    expect(tab("Agent Settings")).toHaveAttribute("aria-selected", "true");
  });

  it("keeps unsaved edits when switching away and back", () => {
    renderTabs();
    fireEvent.change(screen.getByLabelText("Draft"), { target: { value: "half-typed" } });
    fireEvent.click(tab("System Information"));
    fireEvent.click(tab("Agent Settings"));
    expect(screen.getByLabelText("Draft")).toHaveValue("half-typed");
  });
});
