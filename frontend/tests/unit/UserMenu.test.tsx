import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type CurrentUser, api } from "../../src/api/client";
import { UserMenu } from "../../src/components/layout/UserMenu";
import { THEME_CACHE_KEY } from "../../src/lib/theme";
import { unsavedWork } from "../../src/lib/unsavedWork";

/** 027 US1 (FR-001, FR-003, contracts/user-menu-ui.md): the person icon's menu. */

const GUEST = { id: "g1", username: null, is_admin: false, is_active: true } as CurrentUser;
const ALICE = { id: "u1", username: "alice", is_admin: false, is_active: true } as CurrentUser;

let location = "";
function LocationProbe() {
  location = useLocation().pathname;
  return null;
}

function renderMenu(user: CurrentUser, path = "/") {
  vi.spyOn(api, "getCurrentUser").mockResolvedValue(user);
  vi.spyOn(api, "getPreferences").mockResolvedValue({
    schema_version: 1,
    data: { migrated_from_browser: true },
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="*" element={<UserMenu />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function open(name: string) {
  fireEvent.click(await screen.findByRole("button", { name }));
  return screen.findByRole("dialog", { name: "User menu" });
}

afterEach(() => {
  vi.restoreAllMocks();
  unsavedWork.discardAll();
  document.documentElement.classList.remove("dark");
  localStorage.clear();
});

describe("UserMenu", () => {
  it("for a guest: Guest, Log in, and Settings with Colour theme; no Log out or Change user", async () => {
    renderMenu(GUEST);
    const menu = await open("User menu: Guest");
    expect(within(menu).getByText("Guest")).toBeInTheDocument();
    expect(within(menu).getByRole("button", { name: "Log in" })).toBeInTheDocument();
    expect(within(menu).getByText("Settings")).toBeInTheDocument();
    expect(within(menu).getByRole("button", { name: "Colour theme: Dark" })).toBeInTheDocument();
    expect(within(menu).queryByRole("button", { name: "Log out" })).toBeNull();
    expect(within(menu).queryByRole("button", { name: /change user/i })).toBeNull();
  });

  it("for a user: their name, Log out, and Colour theme; no Log in or Change user", async () => {
    renderMenu(ALICE);
    const menu = await open("User menu: alice");
    expect(within(menu).getByText("alice")).toBeInTheDocument();
    expect(within(menu).getByRole("button", { name: "Log out" })).toBeInTheDocument();
    expect(within(menu).getByRole("button", { name: "Colour theme: Dark" })).toBeInTheDocument();
    expect(within(menu).queryByRole("button", { name: "Log in" })).toBeNull();
    expect(within(menu).queryByRole("button", { name: /change user/i })).toBeNull();
  });

  it("shows the name as a label, not a control", async () => {
    renderMenu(ALICE);
    const menu = await open("User menu: alice");
    const label = within(menu).getByText("alice");
    expect(label.closest("button")).toBeNull();
    expect(label).not.toHaveAttribute("tabindex");
  });

  it("Log in closes the menu and opens the login dialog", async () => {
    renderMenu(GUEST);
    const menu = await open("User menu: Guest");
    fireEvent.click(within(menu).getByRole("button", { name: "Log in" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog", { name: "User menu" })).toBeNull());
    expect(await screen.findByLabelText(/username/i)).toBeInTheDocument();
  });
});

describe("UserMenu Log out (027 US3)", () => {
  it("returns to the guest, forgets the theme, and goes to Cloud Pricing", async () => {
    const logOut = vi.spyOn(api, "logOut");
    renderMenu(ALICE, "/trends");
    localStorage.setItem(THEME_CACHE_KEY, JSON.stringify({ user_id: "u1", theme: "dark" }));
    document.documentElement.classList.add("dark");
    const menu = await open("User menu: alice");
    fireEvent.click(within(menu).getByRole("button", { name: "Log out" }));
    expect(logOut).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(THEME_CACHE_KEY)).toBeNull();
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    await vi.waitFor(() => expect(location).toBe("/"));
  });

  it("asks about unsaved work first; Cancel keeps the user logged in", async () => {
    const logOut = vi.spyOn(api, "logOut");
    const discard = vi.fn();
    unsavedWork.register({ id: "svc", label: "the Service tab", save: () => true, discard });
    renderMenu(ALICE);
    const menu = await open("User menu: alice");
    fireEvent.click(within(menu).getByRole("button", { name: "Log out" }));
    const dialog = await screen.findByRole("dialog", { name: /unsaved changes/i });
    expect(within(dialog).getByText("You're logging out.")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(logOut).not.toHaveBeenCalled();
    expect(discard).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog", { name: /unsaved changes/i })).toBeNull();
  });

  it("Discard and continue drops the unsaved work and logs out", async () => {
    const logOut = vi.spyOn(api, "logOut");
    const discard = vi.fn();
    unsavedWork.register({ id: "svc", label: "the Service tab", save: () => true, discard });
    renderMenu(ALICE);
    const menu = await open("User menu: alice");
    fireEvent.click(within(menu).getByRole("button", { name: "Log out" }));
    const dialog = await screen.findByRole("dialog", { name: /unsaved changes/i });
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard and continue" }));
    expect(discard).toHaveBeenCalled();
    expect(logOut).toHaveBeenCalledTimes(1);
  });
});

describe("UserMenu Colour theme (027 US2)", () => {
  it("switches at once and offers the other theme", async () => {
    vi.spyOn(api, "patchPreferences").mockResolvedValue({
      schema_version: 1,
      data: { migrated_from_browser: true },
    });
    renderMenu(GUEST);
    const menu = await open("User menu: Guest");
    fireEvent.click(within(menu).getByRole("button", { name: "Colour theme: Dark" }));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(
      await within(menu).findByRole("button", { name: "Colour theme: Light" }),
    ).toBeInTheDocument();
    expect(api.patchPreferences).not.toHaveBeenCalled();
  });
});
