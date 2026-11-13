/**
 * 023: Cloud Pricing with no architecture named reopens the last one opened, in this session or
 * after a fresh visit; a deleted one leaves the usual empty workspace.
 */
import { expect, test } from "@playwright/test";

import { AWS_EU_WEST_1, Api, openArchitecture } from "./helpers";

test("Cloud Pricing reopens the last architecture opened", async ({ page }) => {
  const user = new Api();
  const first = await user.architecture("aws", "eu-west-1", [AWS_EU_WEST_1]);
  const second = await user.architecture("aws", "eu-west-1", [AWS_EU_WEST_1]);

  await openArchitecture(page, user, first.architectureId);
  await page.goto(`/architectures/${second.architectureId}`);
  await expect(page).toHaveURL(new RegExp(`/architectures/${second.architectureId}$`));

  // In the same session: the Cloud Pricing tab goes back to it, not to an empty workspace.
  await page.getByRole("link", { name: "Cloud Pricing" }).click();
  await expect(page).toHaveURL(new RegExp(`/architectures/${second.architectureId}$`));

  // A return visit to the app's front page: the same.
  await page.goto("/");
  await expect(page).toHaveURL(new RegExp(`/architectures/${second.architectureId}$`));

  // Once it's deleted, Cloud Pricing shows the usual empty workspace.
  await user.call("DELETE", `/architectures/${second.architectureId}`);
  await page.goto("/");
  await expect(page.getByText(/Open or create an architecture/).first()).toBeVisible();
  await expect(page).toHaveURL(/\/$/);
});
