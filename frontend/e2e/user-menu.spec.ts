/**
 * 027 US1 and US3 (contracts/user-menu-ui.md): the user menu from the keyboard, the same as the
 * Cloud Pricing menu; Log in from it; and Log out back to the browser's guest.
 */
import { randomUUID } from "node:crypto";

import { expect, test, type Page } from "@playwright/test";

import { AWS_EU_WEST_1, Api, adminApi } from "./helpers";

const GUEST_KEY = "cloud-pricing-guest-id";
const CURRENT_KEY = "cloud-pricing-current-identity-id";

/** A named account with no password yet: the first login sets it. */
async function newUser(): Promise<{ api: Api; username: string }> {
  const admin = await adminApi();
  const username = `menu-${randomUUID().slice(0, 8)}`;
  const created = await admin.call<{ id: string }>("POST", "/admin/users", { username });
  return { api: new Api(created.id), username };
}

/** Starts this browser as the guest `guestId`. */
async function asGuest(page: Page, guestId: string) {
  await page.addInitScript(
    ([g, c, id]) => {
      if (!localStorage.getItem(c)) {
        localStorage.setItem(g, id);
        localStorage.setItem(c, id);
      }
    },
    [GUEST_KEY, CURRENT_KEY, guestId],
  );
}

const userMenu = (page: Page) => page.getByRole("dialog", { name: "User menu" });

async function logInFromMenu(page: Page, username: string) {
  await page.getByRole("button", { name: "User menu: Guest" }).click();
  await userMenu(page).getByRole("button", { name: "Log in" }).click();
  await page.getByLabel("Username", { exact: true }).fill(username);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("textbox", { name: "Password" }).fill("pw-for-e2e");
  await page.getByRole("button", { name: "Create password & log in" }).click();
  await expect(page.getByRole("button", { name: `User menu: ${username}` })).toBeVisible();
}

test("both header menus work the same way from the keyboard", async ({ page }) => {
  await asGuest(page, randomUUID());
  await page.goto("/");

  // The user menu: Enter, Space and ArrowDown open it; ArrowDown/ArrowUp move; Escape returns.
  const person = page.getByRole("button", { name: "User menu: Guest" });
  for (const key of ["Enter", "Space", "ArrowDown"]) {
    await person.focus();
    await page.keyboard.press(key);
    await expect(userMenu(page)).toBeVisible();
    await expect(userMenu(page).getByRole("button", { name: "Log in" })).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(userMenu(page).getByRole("button", { name: "Colour theme: Dark" })).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(userMenu(page).getByRole("button", { name: "Log in" })).toBeFocused();
    await page.keyboard.press("ArrowUp");
    await expect(userMenu(page).getByRole("button", { name: "Colour theme: Dark" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(userMenu(page)).toHaveCount(0);
    await expect(person).toBeFocused();
  }

  // The Cloud Pricing menu: the same keys.
  const chevron = page.getByRole("button", { name: "Open architecture menu" });
  const architectures = page.getByRole("dialog", { name: "Architectures" });
  for (const key of ["Enter", "Space", "ArrowDown"]) {
    await chevron.focus();
    await page.keyboard.press(key);
    await expect(architectures.getByRole("button", { name: "AWS" })).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(architectures.getByRole("button", { name: "GCP" })).toBeFocused();
    await page.keyboard.press("ArrowUp");
    await expect(architectures.getByRole("button", { name: "AWS" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(architectures).toHaveCount(0);
    await expect(chevron).toBeFocused();
  }
});

test("with reduced motion, the menu opens without animation and the theme without a transition", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await asGuest(page, randomUUID());
  await page.goto("/");
  await page.getByRole("button", { name: "User menu: Guest" }).click();
  const durations = await userMenu(page).evaluate((el) => {
    const style = getComputedStyle(el);
    return [style.animationDuration, style.transitionDuration];
  });
  for (const d of durations) expect(parseFloat(d)).toBeLessThanOrEqual(0.00001);
  await userMenu(page).getByRole("button", { name: "Colour theme: Dark" }).click();
  const bodyTransition = await page.evaluate(() => getComputedStyle(document.body).transitionDuration);
  expect(parseFloat(bodyTransition)).toBeLessThanOrEqual(0.00001);
});

test("log in from the user menu, then log out back to the same guest", async ({ page }) => {
  const guestId = randomUUID();
  const guest = new Api(guestId);
  await guest.architecture("aws", "eu-west-1", [AWS_EU_WEST_1], "Guest's draft");
  const { api: user, username } = await newUser();
  await user.architecture("aws", "eu-west-1", [AWS_EU_WEST_1], "User's own");

  await asGuest(page, guestId);
  await page.goto("/");
  const chevron = page.getByRole("button", { name: "Open architecture menu" });
  const architectures = page.getByRole("dialog", { name: "Architectures" });

  await logInFromMenu(page, username);
  // The user's theme is dark, saved to the account.
  await page.getByRole("button", { name: `User menu: ${username}` }).click();
  await userMenu(page).getByRole("button", { name: "Colour theme: Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.keyboard.press("Escape");
  await chevron.click();
  await architectures.getByRole("button", { name: "AWS" }).click();
  await expect(architectures.getByText("User's own")).toBeVisible();
  await expect(architectures.getByText("Guest's draft")).toHaveCount(0);
  await page.keyboard.press("Escape");

  // Log out: Guest again, the guest's architectures, light, and the account unchanged.
  await page.getByRole("button", { name: `User menu: ${username}` }).click();
  await userMenu(page).getByRole("button", { name: "Log out" }).click();
  await expect(page.getByRole("button", { name: "User menu: Guest" })).toBeVisible();
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  expect(await page.evaluate((k) => localStorage.getItem(k), CURRENT_KEY)).toBe(guestId);
  await chevron.click();
  await architectures.getByRole("button", { name: "AWS" }).click();
  await expect(architectures.getByText("Guest's draft")).toBeVisible();
  await expect(architectures.getByText("User's own")).toHaveCount(0);
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "User menu: Guest" }).click();
  await expect(userMenu(page).getByRole("button", { name: "Log in" })).toBeVisible();
  await expect(userMenu(page).getByRole("button", { name: "Log out" })).toHaveCount(0);
  const prefs = await user.call<{ data: { appearance?: { theme: string } } }>(
    "GET",
    "/me/preferences",
  );
  expect(prefs.data.appearance).toEqual({ theme: "dark" });
});

test("log out with no earlier guest recorded starts a new guest", async ({ page }) => {
  const { username } = await newUser();
  await asGuest(page, randomUUID());
  await page.goto("/");
  await logInFromMenu(page, username);
  await page.evaluate((k) => localStorage.removeItem(k), GUEST_KEY);

  await page.getByRole("button", { name: `User menu: ${username}` }).click();
  await userMenu(page).getByRole("button", { name: "Log out" }).click();
  await expect(page.getByRole("button", { name: "User menu: Guest" })).toBeVisible();
  const ids = await page.evaluate(
    ([g, c]) => [localStorage.getItem(g), localStorage.getItem(c)],
    [GUEST_KEY, CURRENT_KEY],
  );
  expect(ids[0]).toMatch(/^[0-9a-f-]{36}$/);
  expect(ids[1]).toBe(ids[0]);
  await page.getByRole("button", { name: "Open architecture menu" }).click();
  const architectures = page.getByRole("dialog", { name: "Architectures" });
  await architectures.getByRole("button", { name: "AWS" }).click();
  await expect(architectures.getByRole("button", { name: /^Rename / })).toHaveCount(0);
});
