/**
 * 023-agent-foundation in the browser (research R15): with the scripted model, a named user
 * opens the agent panel, starts a session and gets a streamed answer whose figure equals the
 * pricing engine's, sees the operation in the activity log, resizes the panel (kept after a
 * reload), and the panel disappears when the Admin switches the agent off. Runs in its own
 * Playwright project, after the others, because the agent setting is app-wide.
 */
import { randomUUID } from "node:crypto";

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
  await page.getByRole("button", { name: "Open the agent panel" }).click();
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

  // Clarification 1: the bar between canvas and panel moves, and the layout is kept.
  const divider = page.getByRole("separator", { name: "Resize the canvas and the agent panel" });
  await divider.focus();
  await divider.press("ArrowDown");
  await divider.press("ArrowDown");
  await expect(divider).toHaveAttribute("aria-valuenow", "70");
  const corner = page.getByRole("separator", { name: "Resize the agent panel height" });
  const box = (await corner.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y - 40, { steps: 4 });
  await page.mouse.up();
  const panelBox = (await panel(page).boundingBox())!;

  await page.reload();
  await expect(divider).toHaveAttribute("aria-valuenow", "70");
  const reloaded = (await panel(page).boundingBox())!;
  expect(Math.abs(reloaded.height - panelBox.height)).toBeLessThan(3);
  await expect(panel(page).getByText(/This architecture costs/)).toBeVisible();

  // Clarification 4: switched off for everyone, there is no panel at all.
  await admin.call("PUT", "/admin/agent/settings", { ...SETTINGS, agent_enabled: false });
  await page.reload();
  await expect(page.getByRole("button", { name: "Calculate", includeHidden: true })).toBeVisible();
  await expect(panel(page)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open the agent panel" })).toHaveCount(0);
});
