/**
 * 020 User Story 2 in the browser: quickstart C (provider icons, fallback tiles, themes, AWS
 * unchanged, existing layouts kept). The fixture has no GCP or Azure service without an icon,
 * so the fallback tests rewrite the architecture the page loads (patchArchitectureResponse):
 * the tile is drawn entirely by the frontend from the selection's fields.
 *
 * Screenshots of each canvas in light and dark theme are attached to the HTML report
 * (playwright-report/) for a visual check.
 */
import { expect, test, type Page, type TestInfo } from "@playwright/test";

import {
  Api,
  AWS_EU_WEST_1,
  AZURE,
  GCP,
  azureVm,
  canvasIcons,
  expectImagesLoaded,
  gcpMachine,
  iconOf,
  mainCanvas,
  openArchitecture,
  patchArchitectureResponse,
  serviceButton,
  setDarkTheme,
} from "./helpers";

const AZURE_BLOB = {
  service_code: "DZH317F1HKN0",
  sku: "DZH318Z0BPH7/006M/272492b3-1c92-4a5f-bee9-52a8e10ca514",
};
const AZURE_POSTGRES = {
  service_code: "DZH3199QPQTD",
  sku: "DZH318Z0KDZJ/00D3/71f7052a-b259-5928-b57b-d6fbbc1c8cd1",
};

/** Light and dark screenshots of the canvas, attached to the report. */
async function screenshotThemes(page: Page, testInfo: TestInfo, name: string) {
  const canvas = mainCanvas(page);
  for (const dark of [false, true]) {
    await setDarkTheme(page, dark);
    await expectImagesLoaded(canvas);
    const path = testInfo.outputPath(`${name}-${dark ? "dark" : "light"}.png`);
    await canvas.screenshot({ path });
    await testInfo.attach(`${name} (${dark ? "dark" : "light"})`, {
      path,
      contentType: "image/png",
    });
  }
  await setDarkTheme(page, false);
}

test("C1: GCP services show their own Google Cloud icons", async ({ page }, testInfo) => {
  const api = new Api();
  const { architectureId } = await api.architecture("gcp", "us-east1", [
    { ...GCP.n2Core, provider_options: gcpMachine(4, 16) },
    { ...GCP.balancedPd, usage_quantity: "100" },
    { ...GCP.storage, usage_quantity: "100" },
    { ...GCP.sqlCpu },
  ]);
  await openArchitecture(page, api, architectureId);
  const canvas = mainCanvas(page);

  expect(await iconOf(serviceButton(canvas, GCP.n2Core))).toBe("gcp-icons/Compute-Engine");
  // A disk inside Compute Engine gets the more specific icon (FR-008a).
  expect(await iconOf(serviceButton(canvas, GCP.balancedPd))).toBe("gcp-icons/Persistent-Disk");
  expect(await iconOf(serviceButton(canvas, GCP.storage))).toBe("gcp-icons/Cloud-Storage");
  expect(await iconOf(serviceButton(canvas, GCP.sqlCpu))).toBe("gcp-icons/Cloud-SQL");
  expect((await canvasIcons(canvas)).filter((i) => i.startsWith("aws-icons/"))).toEqual([]);
  await screenshotThemes(page, testInfo, "gcp");
});

test("C2: Azure services show their own Azure icons; a managed disk shows Disks", async ({
  page,
}, testInfo) => {
  const api = new Api();
  const { architectureId } = await api.architecture("azure", "eastus", [
    { ...AZURE.vm, provider_options: azureVm("linux") },
    { ...AZURE.diskP10, usage_quantity: "1" },
    { ...AZURE_BLOB, usage_quantity: "100" },
    { ...AZURE_POSTGRES },
    { ...AZURE.egress, usage_quantity: "20" },
  ]);
  await openArchitecture(page, api, architectureId);
  const canvas = mainCanvas(page);

  expect(await iconOf(serviceButton(canvas, AZURE.vm))).toBe("azure-icons/Virtual-Machine");
  expect(await iconOf(serviceButton(canvas, AZURE.diskP10))).toBe("azure-icons/Disks");
  expect(await iconOf(serviceButton(canvas, AZURE_BLOB))).toBe("azure-icons/Storage-Accounts");
  expect(await iconOf(serviceButton(canvas, AZURE_POSTGRES))).toBe(
    "azure-icons/Azure-Database-PostgreSQL-Server",
  );
  expect(await iconOf(serviceButton(canvas, AZURE.egress))).toBe("azure-icons/Azure-Data-Transfer");
  await screenshotThemes(page, testInfo, "azure");
});

test("C3–C5: services without an icon show a provider tile with their own name", async ({
  page,
}, testInfo) => {
  const api = new Api();
  const { architectureId, selectionIds } = await api.architecture("gcp", "us-east1", [
    { ...GCP.n2Core, provider_options: gcpMachine(4, 16) },
    { ...GCP.storage, usage_quantity: "100" },
    { ...GCP.sqlCpu },
  ]);
  const longName =
    "OpenLogic CentOS Stream 9 Linux with Extended Lifecycle Support by an Unusually Long Publisher Name";
  await patchArchitectureResponse(page, architectureId, {
    [selectionIds[1]]: {
      service_code: "A1B2-C3D4-E5F6",
      service_name: longName,
      product_family: "Marketplace Services > OpenLogic",
    },
    [selectionIds[2]]: {
      service_code: "F6E5-D4C3-B2A1",
      service_name: "Bitnami WordPress",
      product_family: "Marketplace Services > Bitnami",
    },
  });
  await openArchitecture(page, api, architectureId);
  const canvas = mainCanvas(page);

  const tiles = canvas.getByTestId("fallback-service-name");
  await expect(tiles).toHaveText([longName, "Bitnami WordPress"]); // C4: each its own name
  const tile = canvas
    .locator("button[aria-pressed]")
    .filter({ has: page.getByTestId("fallback-service-name") })
    .first();
  expect(await iconOf(tile)).toMatch(/^providers\/gcp_icon/);

  // Same size as an icon (the canvas is zoomed, so compare with a real one), and the long name
  // is cut to three lines inside it.
  const size = async (l: typeof tile) => {
    const b = (await l.boundingBox())!;
    return [Math.round(b.width), Math.round(b.height)];
  };
  expect(await size(tile)).toEqual(await size(serviceButton(canvas, GCP.n2Core)));
  await expect(tile).toHaveCSS("width", "60px");
  const clamp = await tiles.first().evaluate((el) => ({
    lines: getComputedStyle(el).webkitLineClamp,
    overflows: el.scrollHeight > el.clientHeight,
  }));
  expect(clamp).toEqual({ lines: "3", overflows: true });
  // Three whole lines fit inside the tile: none is cut through.
  const fit = await tiles.first().evaluate((el) => {
    const name = el.getBoundingClientRect();
    const tileBox = el.closest("button")!.getBoundingClientRect();
    const lineHeight = parseFloat(getComputedStyle(el).lineHeight);
    const zoom = name.height / el.clientHeight;
    return {
      lines: Math.round(el.clientHeight / lineHeight),
      inside: name.bottom <= tileBox.bottom - 1 * zoom,
    };
  });
  expect(fit).toEqual({ lines: 3, inside: true });

  // Hovering shows the full name (FR-009).
  await tile.hover();
  await expect(page.getByRole("tooltip")).toContainText(longName);
  await page.keyboard.press("Escape"); // close it before the screenshots
  await expect(page.getByRole("tooltip")).toHaveCount(0);

  await screenshotThemes(page, testInfo, "gcp-fallback"); // C5
});

test("C6: AWS keeps its icons and its nameless fallback", async ({ page }, testInfo) => {
  const api = new Api();
  const { architectureId, selectionIds } = await api.architecture("aws", "eu-west-1", [
    AWS_EU_WEST_1,
    { ...AWS_EU_WEST_1, usage_quantity: "12" },
  ]);
  await patchArchitectureResponse(page, architectureId, {
    [selectionIds[1]]: { service_code: "ZZNotAService", product_family: null },
  });
  await openArchitecture(page, api, architectureId);
  const canvas = mainCanvas(page);

  expect(await canvasIcons(canvas)).toEqual(["aws-icons/Amazon-EC2", "aws-icons/AWS-Cloud-logo"]);
  await expect(canvas.getByTestId("fallback-service-name")).toHaveCount(0);
  await screenshotThemes(page, testInfo, "aws");
});

test("C7: hand-placed icons and resized boxes keep their place", async ({ page }) => {
  const api = new Api();
  const { architectureId, collectionId, selectionIds } = await api.architecture("gcp", "us-east1", [
    { ...GCP.n2Core, provider_options: gcpMachine(4, 16) },
    { ...GCP.storage, usage_quantity: "1" },
  ]);
  // As v0.0.2 stored them: positions in the browser, keyed by architecture.
  await page.addInitScript(
    ({ arch, coll, sel }) => {
      localStorage.setItem(
        `cloud-pricing-icon-layout-${arch}`,
        JSON.stringify({ [sel]: { x: 130, y: 70 } }),
      );
      localStorage.setItem(
        `cloud-pricing-diagram-layout-${arch}`,
        JSON.stringify({ [coll]: { x: 40, y: 40, width: 367, height: 264 } }),
      );
    },
    { arch: architectureId, coll: collectionId, sel: selectionIds[0] },
  );
  await openArchitecture(page, api, architectureId);
  const canvas = mainCanvas(page);

  const moved = serviceButton(canvas, GCP.n2Core);
  await expect(moved).toHaveCSS("left", "130px");
  await expect(moved).toHaveCSS("top", "70px");
  expect(await iconOf(moved)).toBe("gcp-icons/Compute-Engine");
  const node = canvas.locator(".react-flow__node").filter({ has: serviceButton(page, GCP.n2Core) });
  await expect(node).toHaveCSS("width", "367px");
  await expect(node).toBeVisible();
});

// Found while writing C7, not caused by 020 (the box layout code is unchanged): a box resized to
// about 420 × 320 and then moved is saved correctly, but after a reload React Flow keeps it at
// `visibility: hidden`, so it disappears from the canvas. Smaller boxes, or the same size at
// (0, 0), show. Remove `fixme` once fixed.
test.fixme("a resized and moved box is still visible after a reload", async ({ page }) => {
  const api = new Api();
  const { architectureId, collectionId } = await api.architecture("gcp", "us-east1", [
    { ...GCP.n2Core, provider_options: gcpMachine(4, 16) },
  ]);
  await page.addInitScript(
    ({ arch, coll }) =>
      localStorage.setItem(
        `cloud-pricing-diagram-layout-${arch}`,
        JSON.stringify({ [coll]: { x: 40, y: 40, width: 420, height: 320 } }),
      ),
    { arch: architectureId, coll: collectionId },
  );
  await openArchitecture(page, api, architectureId);
  await expect(mainCanvas(page).locator(".react-flow__node").first()).toBeVisible();
});
