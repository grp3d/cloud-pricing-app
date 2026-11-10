/**
 * 020 quickstart D in the browser: the pop-out canvas shows the same icons as the main one, and
 * a GCP architecture exported and imported resolves its icons the same way.
 */
import { randomUUID } from "node:crypto";

import { expect, test } from "@playwright/test";

import {
  Api,
  AZURE,
  GCP,
  adminApi,
  azureVm,
  canvasIcons,
  expectImagesLoaded,
  gcpMachine,
  mainCanvas,
  openArchitecture,
} from "./helpers";

test("D: the pop-out canvas shows the same icons as the main canvas", async ({ page }) => {
  const api = new Api();
  const { architectureId } = await api.architecture("azure", "eastus", [
    { ...AZURE.vm, provider_options: azureVm("linux") },
    { ...AZURE.diskP10, usage_quantity: "1" },
    { ...AZURE.egress, usage_quantity: "20" },
  ]);
  await openArchitecture(page, api, architectureId);
  const main = await canvasIcons(mainCanvas(page));
  expect(main).toEqual([
    "azure-icons/Virtual-Machine",
    "azure-icons/Disks",
    "azure-icons/Azure-Data-Transfer",
  ]);

  await page
    .getByRole("button", { name: "Open the architecture canvas in an enlarged view" })
    .click();
  const popout = page.getByRole("dialog").locator(".react-flow");
  await expect(popout.locator("button[aria-pressed]")).toHaveCount(3);
  expect(await canvasIcons(popout)).toEqual(main);
  await expectImagesLoaded(popout);
});

test("D: a GCP architecture exported and imported keeps its icons", async ({ page }) => {
  const admin = await adminApi();
  const user = async (prefix: string) => {
    const created = await admin.call<{ id: string }>("POST", "/admin/users", {
      username: `${prefix}-${randomUUID().slice(0, 8)}`,
    });
    return new Api(created.id);
  };
  const owner = await user("e2e-owner");
  const receiver = await user("e2e-receiver");

  const { architectureId } = await owner.architecture(
    "gcp",
    "us-east1",
    [
      { ...GCP.n2Core, provider_options: gcpMachine(4, 16) },
      { ...GCP.balancedPd, usage_quantity: "100" },
      { ...GCP.storage, usage_quantity: "100" },
      { ...GCP.sqlCpu },
    ],
    "Exported GCP",
  );
  const exported = await admin.call<{ architectures: unknown[] }>(
    "GET",
    `/admin/users/${owner.userId}/architectures/export`,
  );
  expect(exported.architectures).toHaveLength(1);
  const imported = await admin.call<{ imported_count: number; failed_count: number }>(
    "POST",
    `/admin/users/${receiver.userId}/architectures/import`,
    exported,
  );
  expect(imported).toMatchObject({ imported_count: 1, failed_count: 0 });
  const [copy] = await receiver.call<{ id: string; name: string }[]>(
    "GET",
    "/architectures?provider=gcp",
  );

  await openArchitecture(page, owner, architectureId);
  const original = await canvasIcons(mainCanvas(page));
  expect(original).toEqual([
    "gcp-icons/Compute-Engine",
    "gcp-icons/Persistent-Disk",
    "gcp-icons/Cloud-Storage",
    "gcp-icons/Cloud-SQL",
  ]);

  const receiverPage = await page.context().browser()!.newPage();
  await openArchitecture(receiverPage, receiver, copy.id);
  expect(await canvasIcons(mainCanvas(receiverPage))).toEqual(original);
  await receiverPage.close();
});
