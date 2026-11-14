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

import { AWS_EU_WEST_1, Api, adminApi, openArchitecture } from "./helpers";

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
