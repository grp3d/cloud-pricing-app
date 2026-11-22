/**
 * 023-agent-foundation in the browser (research R15): with the scripted model, a named user
 * opens the Agent tab, starts a session and gets a streamed answer whose figure equals the
 * pricing engine's, sees the operation in the activity log, moves Agent to the lower half and
 * resizes the panes (kept after a reload), and the Agent tab turns inactive when the Admin
 * switches the agent off. Runs in its own Playwright project, after the others, because the
 * agent setting is app-wide.
 */
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "@playwright/test";

import {
  AWS_EU_WEST_1,
  Api,
  adminApi,
  expectContrast,
  openArchitecture,
  setDarkTheme,
} from "./helpers";

const SETTINGS = {
  agent_enabled: true,
  agent_provider: "scripted",
  agent_model: "scripted",
  agent_base_url: "http://localhost:11434",
  agent_timeout_seconds: 60,
  agent_global_monthly_cap_usd: "10.00",
  agent_default_user_monthly_inputs: 100,
  agent_price_per_input_token_usd: null,
  agent_price_per_output_token_usd: null,
};

function usd(amount: string): string {
  const value = Number(amount);
  return `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const panel = (page: Page) => page.getByRole("region", { name: "Agent" });

test.describe.configure({ mode: "serial" });

test.afterAll(async () => {
  const admin = await adminApi();
  await admin.call("PUT", "/admin/agent/settings", { ...SETTINGS, agent_enabled: false });
});

test("ask the agent about the open architecture", async ({ page }) => {
  const admin = await adminApi();
  await admin.call("PUT", "/admin/agent/settings", SETTINGS);
  const created = await admin.call<{ id: string }>("POST", "/admin/users", {
    username: `agent-${randomUUID().slice(0, 8)}`,
  });
  await admin.call("PATCH", `/admin/users/${created.id}/agent`, { agent_enabled_for_user: true });
  const user = new Api(created.id);
  const { architectureId } = await user.architecture("aws", "eu-west-1", [AWS_EU_WEST_1]);
  const engine = await user.call<{ total_price: string }>(
    "POST",
    `/architectures/${architectureId}/calculate?duration=1_month`,
  );

  await openArchitecture(page, user, architectureId);
  await page.getByRole("tab", { name: "Agent" }).click();
  await panel(page).getByRole("button", { name: "New agent session" }).click();
  await expect(panel(page).getByText(/^Closes /)).toBeVisible();

  await panel(page).getByLabel("Message the agent").fill("What does this cost per month?");
  await panel(page).getByLabel("Message the agent").press("Enter");
  const answer = panel(page).getByText(/This architecture costs/);
  await expect(answer).toContainText(usd(engine.total_price));
  await expect(answer).toContainText("Prices for 1 month (31 days), snapshot");

  await panel(page).getByRole("tab", { name: "Activity" }).click();
  await expect(panel(page).getByText("price_open_architecture")).toBeVisible();
  await expect(panel(page).getByText(/Pricing snapshot: AWS/)).toBeVisible();

  // The Agent tab moves to the lower half (from its options menu), the divider between the
  // panes moves, and the arrangement is kept after a reload.
  await page.getByRole("button", { name: "Agent tab options" }).click();
  await page.getByRole("menuitem", { name: "Move to lower half" }).click();
  await expect(page.getByRole("tablist", { name: "Lower workspace pane" })).toContainText("Agent");
  const divider = page.getByRole("separator", { name: "Resize workspace panes" });
  // Wait for the new position to reach the account before reloading.
  const splitSent = page.waitForRequest(
    (r) =>
      r.url().endsWith("/me/preferences") &&
      r.method() === "PATCH" &&
      JSON.stringify(r.postDataJSON()).includes('"split":0.7'),
  );
  await divider.focus();
  await divider.press("ArrowDown");
  await divider.press("ArrowDown");
  await expect(divider).toHaveAttribute("aria-valuenow", "70");
  expect((await (await splitSent).response())?.ok()).toBe(true);
  await expect(page.locator(".react-flow").first()).toBeVisible();

  await page.reload();
  await expect(divider).toHaveAttribute("aria-valuenow", "70");
  await expect(panel(page).getByText(/This architecture costs/)).toBeVisible();

  // Switched off for everyone: the Agent tab is shown but inactive, and the Canvas fills the
  // pane.
  await admin.call("PUT", "/admin/agent/settings", { ...SETTINGS, agent_enabled: false });
  await page.reload();
  await expect(page.getByRole("button", { name: "Calculate", includeHidden: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Agent" })).toHaveAttribute("aria-disabled", "true");
  await expect(panel(page)).toHaveCount(0);
  await expect(divider).toHaveCount(0);
  await expect(page.locator(".react-flow").first()).toBeVisible();
});

/**
 * 024 (US6, FR-018–FR-021): a comparison's table opens in the Results pane beside the
 * conversation, downloads as CSV with the same figures, steps between results, keeps the
 * divider's position and the open result after a reload, and stacks when the tab is narrow.
 */
test("compare the open architecture with Azure in the Results pane", async ({ page }) => {
  const admin = await adminApi();
  await admin.call("PUT", "/admin/agent/settings", SETTINGS);
  const created = await admin.call<{ id: string }>("POST", "/admin/users", {
    username: `results-${randomUUID().slice(0, 8)}`,
  });
  await admin.call("PATCH", `/admin/users/${created.id}/agent`, { agent_enabled_for_user: true });
  const user = new Api(created.id);
  const { architectureId } = await user.architecture("aws", "eu-west-1", [AWS_EU_WEST_1]);

  await openArchitecture(page, user, architectureId);
  await page.getByRole("tab", { name: "Agent" }).click();
  await panel(page).getByRole("button", { name: "New agent session" }).click();
  await expect(panel(page).getByText(/^Closes /)).toBeVisible();

  const ask = async (question: string) => {
    await panel(page).getByLabel("Message the agent").fill(question);
    await panel(page).getByLabel("Message the agent").press("Enter");
  };
  await ask("What would this cost on Azure?");
  const results = page.getByRole("region", { name: "Results" });
  await expect(results).toBeVisible();
  await expect(panel(page).getByText(/the matched services come to/)).toBeVisible();
  await expect(
    panel(page).getByRole("button", { name: "Show result: E2E aws: AWS vs Azure" }),
  ).toBeVisible();
  await expect(results.getByText("Result 1 of 1")).toBeVisible();
  await expect(results.getByRole("table")).toContainText("Total");

  // The CSV has the same AWS total as the result the pane shows.
  const saved = await user.call<{
    results: { totals: Record<string, { amount: string | null }> }[];
  }>("GET", "/agent/session");
  expect(saved.results[0].totals.aws.amount).not.toBeNull();
  const awsTotal = Number(saved.results[0].totals.aws.amount).toFixed(2);
  const downloaded = page.waitForEvent("download");
  await results.getByRole("button", { name: /Download CSV/ }).click();
  const file = await downloaded;
  expect(file.suggestedFilename()).toMatch(
    /^comparison-e2e-aws-aws-vs-azure-\d{4}-\d{2}-\d{2}\.csv$/,
  );
  const csv = await readFile((await file.path()) as string, "utf-8");
  const totalRow = csv.split("\r\n").find((line) => line.startsWith("Total"));
  expect(totalRow?.split(",")).toContain(awsTotal);
  await expect(results.getByRole("table")).toContainText(
    `$${Number(awsTotal).toLocaleString("en-US", { minimumFractionDigits: 2 })}`,
  );

  // A second comparison: the pane shows it, and steps back to the first.
  await ask("And on Azure again?");
  await expect(results.getByText("Result 2 of 2")).toBeVisible();
  await results.getByRole("button", { name: "Previous result" }).click();
  await expect(results.getByText("Result 1 of 2")).toBeVisible();

  // The divider's position reaches the account and is kept after a reload, and the pane
  // reopens on the latest result.
  const divider = page.getByRole("separator", { name: "Resize conversation and results" });
  const splitSent = page.waitForRequest(
    (r) =>
      r.url().endsWith("/me/preferences") &&
      r.method() === "PATCH" &&
      JSON.stringify(r.postDataJSON()).includes('"agent_results":{"split":0.5}'),
  );
  await divider.focus();
  await divider.press("ArrowRight");
  expect((await (await splitSent).response())?.ok()).toBe(true);
  await page.reload();
  await expect(
    page.getByRole("region", { name: "Results" }).getByText("Result 2 of 2"),
  ).toBeVisible();
  await expect(divider).toHaveAttribute("aria-valuenow", "50");

  // A narrow Agent tab stacks the Results pane under the conversation.
  await page.setViewportSize({ width: 900, height: 1000 });
  await expect(divider).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Results" })).toBeVisible();
});

/**
 * 025 (US2–US4): a change is a proposal in the Results pane; nothing is saved until Accept;
 * Undo and Redo put it back and apply it again; a manual edit ends undo; Reject saves nothing.
 */
test("propose, accept, undo, redo and reject a change", async ({ page }) => {
  const admin = await adminApi();
  await admin.call("PUT", "/admin/agent/settings", SETTINGS);
  const created = await admin.call<{ id: string }>("POST", "/admin/users", {
    username: `changes-${randomUUID().slice(0, 8)}`,
  });
  await admin.call("PATCH", `/admin/users/${created.id}/agent`, { agent_enabled_for_user: true });
  const user = new Api(created.id);
  const { architectureId, selectionIds } = await user.architecture("aws", "eu-west-1", [
    AWS_EU_WEST_1,
  ]);
  const quantity = async () => {
    const detail = await user.call<{
      collections: { sku_selections: { id: string; usage_quantity: string }[] }[];
    }>("GET", `/architectures/${architectureId}`);
    const selection = detail.collections[0].sku_selections.find((s) => s.id === selectionIds[0]);
    return Number(selection?.usage_quantity);
  };
  expect(await quantity()).toBe(24);

  await openArchitecture(page, user, architectureId);
  await page.getByRole("tab", { name: "Agent" }).click();
  await panel(page).getByRole("button", { name: "New agent session" }).click();
  await expect(panel(page).getByText(/^Closes /)).toBeVisible();
  const ask = async (question: string) => {
    await panel(page).getByLabel("Message the agent").fill(question);
    await panel(page).getByLabel("Message the agent").press("Enter");
  };

  await ask("Double the first service.");
  const proposal = page.getByRole("region", { name: "Proposal" });
  await expect(proposal).toBeVisible();
  await expect(panel(page).getByText(/nothing is saved until you accept it/)).toBeVisible();
  await expect(proposal.getByText("Pending")).toBeVisible();
  await expect(proposal.getByText("quantity 24 → 48 Hrs a day")).toBeVisible();
  expect(await quantity()).toBe(24); // nothing saved yet

  await proposal.getByRole("button", { name: "Accept" }).click();
  await expect(proposal.getByText("Accepted")).toBeVisible();
  await expect.poll(quantity).toBe(48);

  await proposal.getByRole("button", { name: "Undo" }).click();
  await expect(proposal.getByRole("button", { name: "Redo" })).toBeVisible();
  await expect.poll(quantity).toBe(24);
  await proposal.getByRole("button", { name: "Redo" }).click();
  await expect(proposal.getByRole("button", { name: "Undo" })).toBeVisible();
  await expect.poll(quantity).toBe(48);

  // A manual edit ends undo, on the card and in the pane.
  await user.call("PATCH", `/sku-selections/${selectionIds[0]}`, { usage_quantity: "30" });
  await page.reload();
  await page.getByRole("tab", { name: "Agent" }).click();
  await expect(
    panel(page)
      .getByText("Your latest edit means the agent's previous change can no longer be undone.")
      .first(),
  ).toBeVisible();
  await expect(panel(page).getByRole("button", { name: "Undo" })).toHaveCount(0);

  // Reject saves nothing.
  await ask("Double the first service again.");
  await expect(proposal.getByText("Pending")).toBeVisible();
  await proposal.getByRole("button", { name: "Reject" }).click();
  await expect(proposal.getByText("Rejected")).toBeVisible();
  expect(await quantity()).toBe(30);
});

/**
 * 026 (US1, US2, US4): a translation is a proposal with its mapping table and cost difference;
 * Accept creates the user's own architecture on the target provider and Undo removes it; the
 * original never changes.
 */
test("translate an architecture to Azure, accept, undo and redo", async ({ page }) => {
  const admin = await adminApi();
  await admin.call("PUT", "/admin/agent/settings", SETTINGS);
  const created = await admin.call<{ id: string }>("POST", "/admin/users", {
    username: `translate-${randomUUID().slice(0, 8)}`,
  });
  await admin.call("PATCH", `/admin/users/${created.id}/agent`, { agent_enabled_for_user: true });
  const user = new Api(created.id);
  const { architectureId } = await user.architecture("aws", "eu-west-1", [AWS_EU_WEST_1]);
  const azureArchitectures = async () =>
    (
      await user.call<{ id: string; provider: string }[]>("GET", "/architectures?provider=azure")
    ).filter((a) => a.provider === "azure").length;
  expect(await azureArchitectures()).toBe(0);

  await openArchitecture(page, user, architectureId);
  await page.getByRole("tab", { name: "Agent" }).click();
  await panel(page).getByRole("button", { name: "New agent session" }).click();
  await expect(panel(page).getByText(/^Closes /)).toBeVisible();
  await panel(page).getByLabel("Message the agent").fill("Translate this architecture to Azure.");
  await panel(page).getByLabel("Message the agent").press("Enter");

  const proposal = page.getByRole("region", { name: "Proposal" });
  await expect(proposal).toBeVisible();
  await expect(proposal.getByText(/^New architecture on Azure: /)).toBeVisible();
  await expect(proposal.getByRole("table", { name: "Mapping" })).toBeVisible();
  await expect(proposal.getByRole("region", { name: "Cost difference" })).toBeVisible();
  await expect(panel(page).getByText(/nothing is created until you accept/)).toBeVisible();
  expect(await azureArchitectures()).toBe(0); // nothing created yet

  await proposal.getByRole("button", { name: "Accept" }).click();
  await expect(proposal.getByText("Accepted")).toBeVisible();
  await expect.poll(azureArchitectures).toBe(1);
  await proposal.getByRole("button", { name: "Undo" }).click();
  await expect(proposal.getByRole("button", { name: "Redo" })).toBeVisible();
  await expect.poll(azureArchitectures).toBe(0);
  await proposal.getByRole("button", { name: "Redo" }).click();
  await expect(proposal.getByRole("button", { name: "Undo" })).toBeVisible();
  await expect.poll(azureArchitectures).toBe(1);
});

/**
 * 026 (FR-012): a translation whose original changed after it was proposed can't be accepted.
 */
test("a translation can't be accepted after the original changes", async ({ page }) => {
  const admin = await adminApi();
  await admin.call("PUT", "/admin/agent/settings", SETTINGS);
  const created = await admin.call<{ id: string }>("POST", "/admin/users", {
    username: `translate-stale-${randomUUID().slice(0, 8)}`,
  });
  await admin.call("PATCH", `/admin/users/${created.id}/agent`, { agent_enabled_for_user: true });
  const user = new Api(created.id);
  const { architectureId, selectionIds } = await user.architecture("aws", "eu-west-1", [
    AWS_EU_WEST_1,
  ]);
  const azureArchitectures = async () =>
    (
      await user.call<{ id: string; provider: string }[]>("GET", "/architectures?provider=azure")
    ).filter((a) => a.provider === "azure").length;

  await openArchitecture(page, user, architectureId);
  await page.getByRole("tab", { name: "Agent" }).click();
  await panel(page).getByRole("button", { name: "New agent session" }).click();
  await expect(panel(page).getByText(/^Closes /)).toBeVisible();
  await panel(page).getByLabel("Message the agent").fill("Translate this architecture to Azure.");
  await panel(page).getByLabel("Message the agent").press("Enter");
  const proposal = page.getByRole("region", { name: "Proposal" });
  await expect(proposal.getByRole("table", { name: "Mapping" })).toBeVisible();

  // The original changes after the translation was proposed.
  await user.call("PATCH", `/sku-selections/${selectionIds[0]}`, { usage_quantity: "30" });
  await proposal.getByRole("button", { name: "Accept" }).click();
  await expect(
    page.getByText("The original or the pricing data changed since this translation.", {
      exact: false,
    }),
  ).toBeVisible();
  expect(await azureArchitectures()).toBe(0);
});

/**
 * 027 (FR-007, SC-002): the Agent tab with a comparison in the Results pane and a pending
 * proposal meets AA contrast in both themes. Then (spec edge case, FR-010) Log out leaves the
 * pending proposal with the user, shows the guest's inactive Agent tab, and saves nothing.
 */
test("the Agent tab meets AA contrast, and Log out keeps a pending proposal", async ({ page }) => {
  const admin = await adminApi();
  await admin.call("PUT", "/admin/agent/settings", SETTINGS);
  const username = `logout-${randomUUID().slice(0, 8)}`;
  const created = await admin.call<{ id: string }>("POST", "/admin/users", { username });
  await admin.call("PATCH", `/admin/users/${created.id}/agent`, { agent_enabled_for_user: true });
  const user = new Api(created.id);
  const { architectureId } = await user.architecture("aws", "eu-west-1", [AWS_EU_WEST_1]);
  const before = await user.call("GET", `/architectures/${architectureId}`);

  await openArchitecture(page, user, architectureId);
  await page.getByRole("tab", { name: "Agent" }).click();
  await panel(page).getByRole("button", { name: "New agent session" }).click();
  await expect(panel(page).getByText(/^Closes /)).toBeVisible();
  const ask = async (question: string) => {
    await panel(page).getByLabel("Message the agent").fill(question);
    await panel(page).getByLabel("Message the agent").press("Enter");
  };
  await ask("What would this cost on Azure?");
  await expect(page.getByRole("region", { name: "Results" }).getByRole("table")).toBeVisible();
  await ask("Double the first service.");
  const proposal = page.getByRole("region", { name: "Proposal" });
  await expect(proposal.getByText("Pending")).toBeVisible();
  for (const dark of [false, true]) {
    await setDarkTheme(page, dark);
    await expectContrast(page, `Agent tab with a proposal (${dark ? "dark" : "light"})`);
  }
  await setDarkTheme(page, false);

  // Log out: back to this browser's own guest (`openArchitecture` stores the user's ID as the
  // guest too, so give the browser a separate guest first). The guest's Agent tab is inactive,
  // and nothing was saved.
  const guestId = randomUUID();
  await page.evaluate((id) => localStorage.setItem("cloud-pricing-guest-id", id), guestId);
  await page.getByRole("button", { name: `User menu: ${username}` }).click();
  await page
    .getByRole("dialog", { name: "User menu" })
    .getByRole("button", { name: "Log out" })
    .click();
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("cloud-pricing-current-identity-id")))
    .toBe(guestId);
  // The menu reads "Guest" briefly while the identity reloads, so check it once the requests
  // have settled: only that proves the browser is the guest. (No reload: `openArchitecture`'s
  // init script would log the user back in.)
  await page.waitForLoadState("networkidle");
  await expect(page.getByRole("button", { name: "User menu: Guest" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Agent" })).toHaveAttribute("aria-disabled", "true");
  expect(await user.call("GET", `/architectures/${architectureId}`)).toEqual(before);

  // The proposal is still the user's, still pending.
  const session = await user.call<{ proposals: { status: string }[] }>("GET", "/agent/session");
  expect(session.proposals.map((p) => p.status)).toContain("pending");
});
