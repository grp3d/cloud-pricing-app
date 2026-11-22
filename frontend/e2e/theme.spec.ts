/**
 * 027 US2 (FR-004 to FR-006, SC-001, SC-003): the colour theme from the user menu. Saved to a
 * logged-in user's account (it follows them to another browser); a guest's lasts until reload.
 */
import { randomUUID } from "node:crypto";

import { expect, test, type Page } from "@playwright/test";

import { adminApi } from "./helpers";

const userMenu = (page: Page) => page.getByRole("dialog", { name: "User menu" });
const html = (page: Page) => page.locator("html");

/** A logged-in browser for a new named user (the token is the user's ID, as after login). */
async function asUser(page: Page, userId: string) {
  await page.addInitScript((id) => {
    localStorage.setItem("cloud-pricing-guest-id", crypto.randomUUID());
    localStorage.setItem("cloud-pricing-current-identity-id", id);
  }, userId);
}

async function pickTheme(page: Page, name: string, theme: "Dark" | "Light") {
  await page.getByRole("button", { name: `User menu: ${name}` }).click();
  await userMenu(page).getByRole("button", { name: `Colour theme: ${theme}` }).click();
}

test("a logged-in user's dark theme switches at once and follows them", async ({ page, browser }) => {
  const admin = await adminApi();
  const username = `theme-${randomUUID().slice(0, 8)}`;
  const { id } = await admin.call<{ id: string }>("POST", "/admin/users", { username });
  await asUser(page, id);
  await page.goto("/");
  await expect(html(page)).not.toHaveClass(/dark/); // never chosen: light (US2-4)

  // SC-001: two clicks, and the whole page changes well within a second, with no navigation.
  const url = page.url();
  await page.getByRole("button", { name: `User menu: ${username}` }).click();
  const item = userMenu(page).getByRole("button", { name: "Colour theme: Dark" });
  const saved = page.waitForRequest(
    (r) => r.url().endsWith("/me/preferences") && r.method() === "PATCH",
  );
  const started = Date.now();
  await item.click();
  await expect(html(page)).toHaveClass(/dark/, { timeout: 1000 });
  expect(Date.now() - started).toBeLessThan(1000);
  expect(page.url()).toBe(url);
  await expect(userMenu(page).getByRole("button", { name: "Colour theme: Light" })).toBeVisible();
  expect((await (await saved).response())?.ok()).toBe(true);

  await page.reload();
  await expect(html(page)).toHaveClass(/dark/);

  // Another browser, the same account: dark (US2-2).
  const other = await browser.newContext();
  const second = await other.newPage();
  await asUser(second, id);
  await second.goto("/");
  await expect(html(second)).toHaveClass(/dark/);
  await other.close();

  // Back to light, and that is saved too.
  // Wait for the save that the click starts; registered first, so a fast save isn't missed.
  const savedLight = page.waitForResponse(
    (r) => r.url().endsWith("/me/preferences") && r.request().method() === "PATCH" && r.ok(),
  );
  await pickTheme(page, username, "Light");
  await expect(html(page)).not.toHaveClass(/dark/);
  await savedLight;
  await page.reload();
  await expect(html(page)).not.toHaveClass(/dark/);
});

test("a guest's theme is not saved", async ({ page }) => {
  await page.addInitScript((id) => {
    if (!localStorage.getItem("cloud-pricing-current-identity-id")) {
      localStorage.setItem("cloud-pricing-guest-id", id);
      localStorage.setItem("cloud-pricing-current-identity-id", id);
    }
  }, randomUUID());
  const patches: string[] = [];
  page.on("request", (r) => {
    if (r.url().endsWith("/me/preferences") && r.method() === "PATCH") {
      patches.push(r.postData() ?? "");
    }
  });
  await page.goto("/");
  await pickTheme(page, "Guest", "Dark");
  await expect(html(page)).toHaveClass(/dark/);
  await page.reload();
  await expect(html(page)).not.toHaveClass(/dark/);
  expect(patches.filter((p) => p.includes("appearance"))).toEqual([]);
});
