/**
 * 021 in the browser: quickstart A (the header architecture menu), B (three zones and which
 * inspector tab comes forward), C (split, merge and swap by mouse and keyboard, restored on
 * reload) and D (widths at 1280 and 1600, no sideways scroll, light and dark screenshots).
 */
import { randomUUID } from "node:crypto";

import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

import {
  AWS_EU_WEST_1,
  Api,
  GCP,
  adminApi,
  calculate,
  openArchitecture,
  serviceButton,
  showPricing,
} from "./helpers";

/** A named (non-guest) user, so the sharing and Import actions are offered. */
async function namedUser(prefix: string): Promise<Api> {
  const admin = await adminApi();
  const created = await admin.call<{ id: string }>("POST", "/admin/users", {
    username: `${prefix}-${randomUUID().slice(0, 8)}`,
  });
  return new Api(created.id);
}

async function makePublic(api: Api, id: string) {
  await api.call("PATCH", `/architectures/${id}`, { is_public: true });
}

const menuButton = (page: Page) => page.getByRole("button", { name: "Open architecture menu" });
const menu = (page: Page) => page.getByRole("dialog", { name: "Architectures" });
const tab = (page: Page, name: "Pricing" | "Service") => page.getByRole("tab", { name });
const inspector = (page: Page) => page.getByRole("complementary", { name: "Inspector" });

async function openMenu(page: Page) {
  await menuButton(page).click();
  await expect(menu(page)).toBeVisible();
}

/** 021 US6: providers start collapsed; hovering one shows its panel to the right. */
async function showGroup(page: Page, provider: "AWS" | "GCP" | "Azure") {
  await menu(page).getByRole("button", { name: provider, exact: true }).hover();
  const group = menu(page).getByRole("group", { name: `${provider} architectures` });
  await expect(group).toBeVisible();
  return group;
}

test("A: the header menu opens, creates, imports and deletes, from any page", async ({ page }) => {
  const api = await namedUser("menu");
  const { architectureId: awsId } = await api.architecture("aws", "us-east-1", [], "Web App");
  const { architectureId: gcpId } = await api.architecture("gcp", "us-east1", [], "Data Lake");

  const sharer = await namedUser("sharer");
  const sharedGcp = await sharer.architecture("gcp", "us-east1", [], "Shared GCP");
  const sharedAws = await sharer.architecture("aws", "us-east-1", [], "Shared AWS");
  await makePublic(sharer, sharedGcp.architectureId);
  await makePublic(sharer, sharedAws.architectureId);

  await openArchitecture(page, api, awsId);
  await expect(page.getByLabel("AWS · Web App")).toBeVisible();
  // No architecture column in the workspace any more (FR-007).
  await expect(page.getByRole("region", { name: "Cloud providers" })).toHaveCount(0);

  // A1–A2: three collapsed providers; picking a GCP architecture opens it and switches the
  // provider.
  await openMenu(page);
  for (const name of ["AWS", "GCP", "Azure"]) {
    await expect(menu(page).getByRole("button", { name, exact: true })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  }
  await expect(menu(page).getByRole("group")).toHaveCount(0);
  await (
    await showGroup(page, "GCP")
  )
    .getByRole("button", { name: "Data Lake", exact: true })
    .click();
  await expect(menu(page)).toBeHidden();
  await expect(page).toHaveURL(new RegExp(`/architectures/${gcpId}$`));
  await expect(page.getByLabel("GCP · Data Lake")).toBeVisible();

  // A3: New Azure architecture, Escape clears the name first, Enter creates.
  await openMenu(page);
  await showGroup(page, "Azure");
  await menu(page).getByRole("button", { name: "New Azure architecture…" }).click();
  const field = menu(page).getByLabel("New Azure architecture name");
  await field.fill("Draft");
  await field.press("Escape");
  await expect(menu(page)).toBeVisible();
  await menu(page).getByRole("button", { name: "New Azure architecture…" }).click();
  await menu(page).getByLabel("New Azure architecture name").fill("Edge Cache");
  await menu(page).getByLabel("New Azure architecture name").press("Enter");
  await expect(page.getByLabel("Azure · Edge Cache")).toBeVisible();

  // A5: Import in the GCP group lists only GCP architectures.
  await openMenu(page);
  await showGroup(page, "GCP");
  await menu(page).getByRole("button", { name: "Import a GCP architecture" }).click();
  const importDialog = page.getByRole("dialog", { name: "Import a GCP architecture" });
  await expect(importDialog.getByRole("button", { name: "Shared GCP", exact: true })).toBeVisible();
  await expect(importDialog.getByRole("button", { name: "Shared AWS", exact: true })).toHaveCount(
    0,
  );
  await page.keyboard.press("Escape");

  // A4: deleting the open architecture asks first, then returns to the empty workspace.
  await openMenu(page);
  await showGroup(page, "Azure");
  await menu(page).getByRole("button", { name: "Delete Edge Cache" }).click();
  await page.getByRole("button", { name: /^Delete$/ }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByText(/from the Cloud Pricing menu/).first()).toBeVisible();

  // A6: on Trends, "Cloud Pricing" goes to the workspace and the chevron opens the menu.
  await page.getByRole("link", { name: "Trends" }).click();
  await expect(page).toHaveURL(/\/trends$/);
  await openMenu(page);
  await showGroup(page, "AWS");
  await menu(page).getByRole("button", { name: "Web App", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/architectures/${awsId}$`));

  // A7: keyboard only — open with Enter, into a provider with ArrowRight, back with
  // ArrowLeft, close with Escape, focus back on the chevron.
  await menuButton(page).focus();
  await page.keyboard.press("Enter");
  await expect(menu(page)).toBeVisible();
  await menu(page).getByRole("button", { name: "AWS", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    menu(page).getByRole("group", { name: "AWS architectures" }).getByRole("button", {
      name: "Web App",
      exact: true,
    }),
  ).toBeFocused();
  await page.keyboard.press("ArrowLeft");
  await expect(menu(page).getByRole("button", { name: "AWS", exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(menu(page)).toBeHidden();
  await expect(menuButton(page)).toBeFocused();
});

test("B: selecting brings Service forward, a save keeps it, a calculation brings Pricing", async ({
  page,
}) => {
  const api = new Api();
  const { architectureId } = await api.architecture("aws", "eu-west-1", [AWS_EU_WEST_1]);
  const second = await api.architecture("aws", "eu-west-1", [AWS_EU_WEST_1], "E2E aws second");
  await openArchitecture(page, api, architectureId);

  // The automatic calculation on open finished with Pricing in front.
  await expect(tab(page, "Pricing")).toHaveAttribute("aria-selected", "true");

  // B2: selecting the service brings Service forward; saving keeps it there (FR-017).
  await serviceButton(page, AWS_EU_WEST_1).click();
  await expect(tab(page, "Service")).toHaveAttribute("aria-selected", "true");
  await page.getByLabel(/^(Usage quantity|Hours per day)/).fill("12");
  const saved = page.waitForResponse(
    (r) => /\/sku-selections\/[^/]+$/.test(r.url()) && r.request().method() === "PATCH",
  );
  await page.getByRole("button", { name: "Save" }).click();
  expect((await saved).ok()).toBe(true);
  await expect(tab(page, "Service")).toHaveAttribute("aria-selected", "true");
  // 021 US5 (FR-038): the saved service stays open.
  await expect(page.getByLabel(/^(Usage quantity|Hours per day)/)).toHaveValue("12");

  // B3: Calculate (from the Pricing tab) shows the new total.
  await calculate(page);
  await expect(tab(page, "Pricing")).toHaveAttribute("aria-selected", "true");

  // B6: collapsed, selecting a service expands the inspector with Service in front.
  await inspector(page).getByRole("button", { name: "Collapse inspector" }).click();
  await expect(inspector(page).getByRole("button", { name: "Expand inspector" })).toBeVisible();
  await serviceButton(page, AWS_EU_WEST_1).click();
  await expect(tab(page, "Service")).toHaveAttribute("aria-selected", "true");

  // B6: collapsed, a calculation (the automatic one on opening another architecture) leaves
  // it collapsed and marks the rail.
  // Wait for the collapsed state to reach the account before reloading the page.
  const collapsedSaved = page.waitForResponse(
    (r) =>
      r.url().endsWith("/me/preferences") &&
      r.request().method() === "PATCH" &&
      JSON.stringify(r.request().postDataJSON()).includes('"col4":true'),
  );
  await inspector(page).getByRole("button", { name: "Collapse inspector" }).click();
  await collapsedSaved;
  await page.goto(`/architectures/${second.architectureId}`);
  await expect(inspector(page).getByRole("button", { name: "Pricing — new result" })).toBeVisible();
  await expect(page.getByRole("tablist")).toHaveCount(0);
  await inspector(page).getByRole("button", { name: "Pricing — new result" }).click();
  await expect(tab(page, "Pricing")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("region", { name: "Calculation result" })).toBeVisible();
});

/** Drags `name`'s tab to a point in the inspector, as a fraction of its height. */
async function dragTab(page: Page, from: ReturnType<Page["getByRole"]>, toFraction: number) {
  const source = await from.boundingBox();
  const target = await inspector(page).boundingBox();
  if (!source || !target) throw new Error("no layout");
  await page.mouse.move(source.x + source.width / 2, source.y + source.height / 2);
  await page.mouse.down();
  await page.mouse.move(source.x + source.width / 2 + 10, source.y + source.height / 2 + 10);
  await page.mouse.move(target.x + target.width / 2, target.y + target.height * toFraction, {
    steps: 8,
  });
  await page.mouse.up();
}

test("C: split, swap and merge by drag and by keyboard, restored after a reload", async ({
  page,
}) => {
  const api = new Api();
  const { architectureId } = await api.architecture("aws", "eu-west-1", [AWS_EU_WEST_1]);
  await openArchitecture(page, api, architectureId);
  const upper = page.getByRole("tablist", { name: "Upper inspector pane" });
  const lower = page.getByRole("tablist", { name: "Lower inspector pane" });

  // C1: drag Service to the lower half.
  await dragTab(page, tab(page, "Service"), 0.8);
  await expect(lower.getByRole("tab", { name: "Service" })).toBeVisible();
  await expect(upper.getByRole("tab", { name: "Pricing" })).toBeVisible();

  // C6: the split survives a reload (saved to the account).
  await page.reload();
  await expect(lower.getByRole("tab", { name: "Service" })).toBeVisible();

  // C3: drag the upper tab to the lower half: the panes swap.
  await dragTab(page, upper.getByRole("tab"), 0.8);
  await expect(upper.getByRole("tab", { name: "Service" })).toBeVisible();

  // C5: a drag cancelled with Escape changes nothing.
  const box = (await lower.getByRole("tab").boundingBox())!;
  await page.mouse.move(box.x + 5, box.y + 5);
  await page.mouse.down();
  await page.mouse.move(box.x + 30, box.y - 200, { steps: 5 });
  await page.keyboard.press("Escape");
  await page.mouse.up();
  await expect(upper.getByRole("tab", { name: "Service" })).toBeVisible();

  // C4: drag the lower tab onto the upper bar: merged, with it in front.
  const inspectorBox = (await inspector(page).boundingBox())!;
  await dragTab(page, lower.getByRole("tab"), 15 / inspectorBox.height);
  await expect(page.getByRole("tablist", { name: "Inspector tabs" })).toBeVisible();
  await expect(tab(page, "Pricing")).toHaveAttribute("aria-selected", "true");

  // C7: keyboard only — Move to lower half, Swap, Merge.
  await page.getByRole("button", { name: "Pricing tab options" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("menuitem", { name: "Move to lower half" }).click();
  await expect(lower.getByRole("tab", { name: "Pricing" })).toBeVisible();
  await page.getByRole("button", { name: "Service tab options" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("menuitem", { name: "Swap" }).click();
  await expect(upper.getByRole("tab", { name: "Pricing" })).toBeVisible();
  await page.getByRole("button", { name: "Service tab options" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("menuitem", { name: "Merge" }).click();
  await expect(tab(page, "Service")).toHaveAttribute("aria-selected", "true");

  // C2: the divider moves from the keyboard too.
  await page.getByRole("button", { name: "Service tab options" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("menuitem", { name: "Move to lower half" }).click();
  const divider = page.getByRole("separator", { name: "Resize inspector panes" });
  await expect(divider).toHaveAttribute("aria-valuenow", "50");
  await divider.focus();
  await page.keyboard.press("ArrowDown");
  await expect(divider).toHaveAttribute("aria-valuenow", "55");
});

async function noSidewaysScroll(page: Page) {
  // Polled: after a viewport change the zones refit on the next resize notification.
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      ),
    )
    .toBeLessThanOrEqual(0);
}

async function canvasWidth(page: Page): Promise<number> {
  const box = await page.locator(".react-flow").first().boundingBox();
  return box?.width ?? 0;
}

async function attachScreenshots(page: Page, testInfo: TestInfo, label: string) {
  // Reduced motion (FR-032) makes the theme switch below instant, so the screenshot isn't
  // taken while colours are still transitioning.
  await page.emulateMedia({ reducedMotion: "reduce" });
  await testInfo.attach(`${label} — light`, {
    body: await page.screenshot(),
    contentType: "image/png",
  });
  await page.evaluate(() => document.documentElement.classList.add("dark"));
  // Screenshots only (nothing is asserted on them): let the theme switch repaint first.
  await page.waitForTimeout(300);
  await testInfo.attach(`${label} — dark`, {
    body: await page.screenshot(),
    contentType: "image/png",
  });
  await page.evaluate(() => document.documentElement.classList.remove("dark"));
  await page.waitForTimeout(300);
}

test("D: widths at 1280 and 1600, no sideways scroll, light and dark", async ({
  page,
}, testInfo) => {
  const api = new Api();
  const { architectureId } = await api.architecture("aws", "eu-west-1", [AWS_EU_WEST_1]);

  await page.setViewportSize({ width: 1600, height: 1000 });
  await openArchitecture(page, api, architectureId);
  // SC-001: at least 900px of canvas at 1600 (the canvas has 8px of padding each side).
  expect(await canvasWidth(page)).toBeGreaterThanOrEqual(880);
  await noSidewaysScroll(page);
  await attachScreenshots(page, testInfo, "Workspace at 1600");

  await page.setViewportSize({ width: 1280, height: 800 });
  // FR-030: about 600px of canvas at 1280 (wait for the refit: it was 920px at 1600).
  await expect.poll(() => canvasWidth(page)).toBeLessThan(700);
  expect(await canvasWidth(page)).toBeGreaterThanOrEqual(570);
  await noSidewaysScroll(page);
  await attachScreenshots(page, testInfo, "Workspace at 1280");

  // SC-008: Trends and Admin don't scroll sideways at 1280 either.
  await page.getByRole("link", { name: "Trends" }).click();
  await expect(page).toHaveURL(/\/trends$/);
  await noSidewaysScroll(page);
  await attachScreenshots(page, testInfo, "Trends at 1280");

  const admin = await adminApi();
  await page.addInitScript((id) => {
    localStorage.setItem("cloud-pricing-guest-id", id);
    localStorage.setItem("cloud-pricing-current-identity-id", id);
  }, admin.userId);
  await page.goto("/admin");
  await expect(page.getByRole("link", { name: "Admin" })).toBeVisible();
  await noSidewaysScroll(page);
  await attachScreenshots(page, testInfo, "Admin at 1280");
});

test("E: one-click add, Save and Calculate colours, and rename (US5, US6)", async ({ page }) => {
  const api = await namedUser("refine");
  // One priced service already, so the automatic first calculation has run (and brought
  // Pricing forward) before the new service is added.
  const { architectureId } = await api.architecture(
    "aws",
    "eu-west-1",
    [AWS_EU_WEST_1],
    "Refine Me",
  );
  await openArchitecture(page, api, architectureId);
  await expect(page.getByRole("heading", { name: "AWS · Refine Me" })).toBeVisible();
  await expect(tab(page, "Pricing")).toHaveAttribute("aria-selected", "true");

  // The header is the dark band, and no longer names the architecture (FR-035, FR-036).
  const banner = page.getByRole("banner");
  await expect(banner.getByText("Refine Me")).toHaveCount(0);
  const headerBg = await banner.evaluate((el) => getComputedStyle(el).backgroundColor);
  const bodyBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(headerBg).not.toBe(bodyBg);

  // Priced and current: Calculate is light blue (FR-040).
  const calculateButton = page.getByRole("button", { name: "Calculate", includeHidden: true });
  await expect(calculateButton).toHaveAttribute("data-variant", "soft");

  // E1: select the box, search, click a result's arrow: the service is added (FR-037).
  await page
    .locator(".react-flow__node")
    .filter({ hasText: "App" })
    .first()
    .click({
      position: { x: 12, y: 8 },
    });
  await page.getByPlaceholder("Service code (e.g. AmazonEC2)").fill("AmazonEC2");
  const added = page.waitForResponse(
    (r) => /\/collections\/[^/]+\/sku-selections$/.test(r.url()) && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: /^Add / }).first().click();
  const body = (await added).request().postDataJSON();
  expect(body).toMatchObject({ pricing_term: "on_demand", usage_quantity: "730" });
  await expect(tab(page, "Service")).toHaveAttribute("aria-selected", "true");
  // The architecture changed, so Calculate turns dark blue.
  await expect(calculateButton).toHaveAttribute("data-variant", "default");

  // E2: Save is light blue until a field changes; after saving it stays open (FR-038, FR-039).
  const save = page.getByRole("button", { name: "Save" });
  await expect(save).toHaveAttribute("data-variant", "soft");
  await page.getByLabel(/^Usage quantity/).fill("100");
  await expect(save).toHaveAttribute("data-variant", "default");
  await save.click();
  await expect(save).toHaveAttribute("data-variant", "soft");
  await expect(page.getByLabel(/^Usage quantity/)).toHaveValue("100");

  // E3: after a calculation Calculate is light blue again (FR-040).
  await calculate(page);
  await expect(calculateButton).toHaveAttribute("data-variant", "soft");

  // E4: rename from the menu (FR-043); the canvas title follows.
  await openMenu(page);
  const aws = await showGroup(page, "AWS");
  const renameButton = aws.getByRole("button", { name: "Rename Refine Me" });
  const shareButton = aws.getByRole("button", { name: "Make Refine Me public" });
  const deleteButton = aws.getByRole("button", { name: "Delete Refine Me" });
  const [share, rename, del] = await Promise.all(
    [shareButton, renameButton, deleteButton].map((b) => b.boundingBox()),
  );
  expect(share!.x).toBeLessThan(rename!.x);
  expect(rename!.x).toBeLessThan(del!.x);
  await renameButton.click();
  const field = aws.getByLabel("Name for Refine Me");
  await expect(field).toBeFocused();
  await field.fill("Refined");
  await field.press("Enter");
  await expect(aws.getByRole("button", { name: "Refined", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("heading", { name: "AWS · Refined" })).toBeVisible();
});

test("F: GCP services are named on the canvas, in the Service tab and in the price list (US7)", async ({
  page,
}) => {
  const api = new Api();
  const { architectureId } = await api.architecture("gcp", "us-east1", [GCP.storage]);
  await openArchitecture(page, api, architectureId);

  const icon = serviceButton(page, GCP.storage);
  const name = await icon.getAttribute("aria-label");
  expect(name).toMatch(/^Cloud Storage, /);
  expect(name).toContain(`${GCP.storage.service_code} / ${GCP.storage.sku}`);

  // The hover text leads with the name; the codes line is muted.
  await icon.hover();
  const tooltip = page.getByRole("tooltip");
  await expect(tooltip).toContainText("Cloud Storage");
  await expect(
    tooltip.getByText(`${GCP.storage.service_code} / ${GCP.storage.sku}`, { exact: true }),
  ).toHaveClass(/opacity-70/);

  // The Service tab heading names it; the codes sit muted below.
  await icon.click();
  await expect(page.getByRole("heading", { level: 3, name: /^Cloud Storage/ })).toBeVisible();

  // The price list names it too.
  await calculate(page);
  await expect(
    page.getByRole("region", { name: "Calculation result" }).getByText(/^Cloud Storage — /),
  ).toBeVisible();
});

test("G: the Service and Pricing tab tops stay in place while the rest scrolls (US8)", async ({
  page,
}) => {
  const api = new Api();
  const { architectureId } = await api.architecture("aws", "eu-west-1", [AWS_EU_WEST_1]);
  // Short enough that both tabs overflow.
  await page.setViewportSize({ width: 1280, height: 520 });
  await openArchitecture(page, api, architectureId);

  async function scrollsUnder(pinned: string, scroll: string, keep: Locator) {
    const area = page.getByTestId(scroll);
    const before = await page.getByTestId(pinned).boundingBox();
    expect(await area.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
    await area.evaluate((el) => el.scrollTo(0, el.scrollHeight));
    expect(await area.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
    expect(await page.getByTestId(pinned).boundingBox()).toEqual(before);
    await expect(keep).toBeInViewport();
  }

  // Service: the heading and the delete button stay; the form scrolls up into view.
  await serviceButton(page, AWS_EU_WEST_1).click();
  await scrollsUnder(
    "service-pinned",
    "service-scroll",
    page.getByRole("button", { name: "Remove this service" }),
  );
  await expect(page.getByRole("button", { name: "Save" })).toBeInViewport();

  // Pricing: duration, Calculate and the total stay. One priced line is short, so the window
  // is made shorter still for it to overflow.
  await showPricing(page);
  await page.setViewportSize({ width: 1280, height: 300 });
  await scrollsUnder(
    "pricing-pinned",
    "pricing-scroll",
    page.getByRole("heading", { name: /^Total:/ }),
  );
  await expect(page.getByText(/^Data Timestamp:/)).toBeInViewport();
});

test("H: the canvas hover text keeps its size at any zoom (US9)", async ({ page }) => {
  const api = new Api();
  const { architectureId } = await api.architecture("aws", "eu-west-1", [AWS_EU_WEST_1]);
  await openArchitecture(page, api, architectureId);
  const icon = serviceButton(page, AWS_EU_WEST_1);
  const content = page.locator('[data-slot="tooltip-content"]');

  // Focus opens the same pop-up as hovering, and works wherever the zoom puts the icon.
  async function popupFontSize() {
    await page.getByRole("button", { name: "Zoom Out" }).focus();
    await expect(content).toHaveCount(0);
    await icon.focus();
    await expect(content).toBeVisible();
    return content.evaluate((el) => getComputedStyle(el).fontSize);
  }

  // The zoom readout ("100%") shows the zoom really changed.
  const readout = page.getByText(/^\d+%$/);
  async function zoom(name: "Zoom In" | "Zoom Out") {
    const button = page.getByRole("button", { name });
    for (let i = 0; i < 4 && (await button.isEnabled()); i++) await button.click();
  }

  const atDefault = await popupFontSize();
  expect(atDefault).toBe("12px");
  await expect(readout).toHaveText("100%");
  await zoom("Zoom In");
  await expect(readout).not.toHaveText("100%");
  expect(await popupFontSize()).toBe(atDefault);
  await zoom("Zoom Out");
  await zoom("Zoom Out");
  expect(parseInt((await readout.textContent()) ?? "100")).toBeLessThan(100);
  expect(await popupFontSize()).toBe(atDefault);
});
