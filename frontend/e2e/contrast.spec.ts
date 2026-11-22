/**
 * 027 (FR-007, SC-002, research R4): WCAG 2.1 AA colour contrast on every page, dialog and menu,
 * in the light and the dark theme, checked on the rendered page with axe. The Agent tab and its
 * Results pane are checked in `agent.spec.ts`, where the agent is switched on.
 */
import { expect, test } from "@playwright/test";

import {
  AWS_EU_WEST_1,
  adminApi,
  expectContrast,
  openArchitecture,
  setDarkTheme,
} from "./helpers";


for (const dark of [false, true]) {
  const theme = dark ? "dark" : "light";

  test(`pages, dialogs and menus meet AA contrast (${theme})`, async ({ page }) => {
    const admin = await adminApi();
    const { architectureId } = await admin.architecture("aws", "eu-west-1", [AWS_EU_WEST_1]);
    await openArchitecture(page, admin, architectureId);
    await setDarkTheme(page, dark);
    await expectContrast(page, `workspace (${theme})`);

    await page.getByRole("button", { name: "Open architecture menu" }).click();
    await page
      .getByRole("dialog", { name: "Architectures" })
      .getByRole("button", { name: "AWS" })
      .click();
    await expectContrast(page, `architecture menu (${theme})`);
    await page.keyboard.press("Escape");

    await page.getByRole("button", { name: "User menu: Admin" }).click();
    await expectContrast(page, `user menu (${theme})`);
    await page.keyboard.press("Escape");

    // A dialog: delete confirmation from the architecture menu.
    await page.getByRole("button", { name: "Open architecture menu" }).click();
    const menu = page.getByRole("dialog", { name: "Architectures" });
    await menu.getByRole("button", { name: "AWS" }).click();
    await menu.getByRole("button", { name: /^Delete / }).first().click();
    const confirm = page.getByRole("dialog").filter({ hasText: "can't be undone" });
    await expect(confirm).toBeVisible();
    await expectContrast(page, `confirmation dialog (${theme})`);
    await confirm.getByRole("button", { name: "Cancel" }).click();

    await page.getByRole("link", { name: "Trends" }).click();
    await expect(page.locator("#trends-charts")).toBeVisible();
    await setDarkTheme(page, dark);
    await expectContrast(page, `Trends (${theme})`);

    await page.getByRole("link", { name: "Admin" }).click();
    await expect(page.getByRole("tab").first()).toBeVisible();
    await setDarkTheme(page, dark);
    const adminTabs = page.getByRole("tablist", { name: "Admin sections" }).getByRole("tab");
    for (const tab of await adminTabs.all()) {
      await tab.click();
      await expectContrast(page, `Admin, ${await tab.textContent()} (${theme})`);
    }
    // 027 US6: System Information's own tabs.
    await page.getByRole("tab", { name: "System Information" }).click();
    const sections = page.getByRole("tablist", { name: "System Information sections" });
    for (const tab of await sections.getByRole("tab").all()) {
      await tab.click();
      await expectContrast(page, `System Information, ${await tab.textContent()} (${theme})`);
    }
  });
}
