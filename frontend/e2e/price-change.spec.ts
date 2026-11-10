/**
 * 020 User Story 1 in the browser: quickstart A (Price Change follows every priced input) and
 * B (last calculations stored by v0.0.2). Quantities are hours per day; a month is 31 days and
 * a year 365. Rates are the fixture's: N2 core $0.031611/h, N2 RAM $0.004237/GiB-h, Azure D4s v5
 * Linux $0.192/h and Windows $0.376/h, AWS eu-west-1 EC2 $0.2116/h.
 */
import { expect, test, type Page } from "@playwright/test";

import {
  Api,
  AWS_EU_WEST_1,
  AZURE,
  GCP,
  azureVm,
  calculate,
  editService,
  gcpMachine,
  openArchitecture,
  pricing,
} from "./helpers";

test("A1–A5: a GCP machine's vCPUs and memory move Price Change, also across a Duration switch", async ({
  page,
}) => {
  const api = new Api();
  const { architectureId } = await api.architecture("gcp", "us-east1", [
    { ...GCP.n2Core, provider_options: gcpMachine(2, 8) },
  ]);
  await openArchitecture(page, api, architectureId);
  const p = pricing(page);

  // A1: (2 × 0.031611 + 8 × 0.004237) × 744 = 72.255792
  await calculate(page, "1 month");
  await expect(p.total).toHaveText("Total: 72.26 USD");
  await expect(p.priceChange).toHaveCount(0);

  // A2: 4 vCPUs → 119.29296, Price Change +47.037168
  await editService(page, GCP.n2Core, { vcpus: 4 });
  await expect(p.outOfDate).toBeVisible();
  await calculate(page);
  await expect(p.total).toHaveText("Total: 119.29 USD");
  await expect(p.priceChange).toHaveText("Price Change: +47.04");
  await expect(p.outOfDate).toHaveCount(0);

  // A3: 16 GiB → 144.511584, Price Change +25.218624
  await editService(page, GCP.n2Core, { memoryGib: 16 });
  await calculate(page);
  await expect(p.total).toHaveText("Total: 144.51 USD");
  await expect(p.priceChange).toHaveText("Price Change: +25.22");

  // A4: saving the same memory again is no change: no notice, Price Change kept.
  await editService(page, GCP.n2Core, { memoryGib: 16 });
  await expect(p.outOfDate).toHaveCount(0);
  await calculate(page);
  await expect(p.priceChange).toHaveText("Price Change: +25.22");

  // A5: 8 vCPUs, then Yearly. New: (8 × 0.031611 + 16 × 0.004237) × 8760 = 2,809.1568.
  // Previous contents (4 / 16) re-priced yearly in us-east1: 1,701.50736. Change +1,107.64944.
  await editService(page, GCP.n2Core, { vcpus: 8 });
  await expect(p.outOfDate).toBeVisible();
  await calculate(page, "1 year");
  await expect(p.total).toHaveText("Total: 2,809.16 USD");
  await expect(p.priceChange).toHaveText("Price Change: +1,107.65");
});

test("A6: switching an Azure VM from Linux to Windows moves Price Change", async ({ page }) => {
  const api = new Api();
  const { architectureId } = await api.architecture("azure", "eastus", [
    { ...AZURE.vm, provider_options: azureVm("linux") },
  ]);
  await openArchitecture(page, api, architectureId);
  const p = pricing(page);

  await calculate(page, "1 month");
  await expect(p.total).toHaveText("Total: 142.85 USD"); // 744 × 0.192
  await editService(page, AZURE.vm, { os: "windows" });
  await expect(p.outOfDate).toBeVisible();
  await calculate(page);
  await expect(p.total).toHaveText("Total: 279.74 USD"); // 744 × 0.376
  await expect(p.priceChange).toHaveText("Price Change: +136.90");
});

test("A7: an AWS box outside us-east-1 is re-priced in its own region after a Duration switch", async ({
  page,
}) => {
  const api = new Api();
  const { architectureId } = await api.architecture("aws", "eu-west-1", [AWS_EU_WEST_1]);
  await openArchitecture(page, api, architectureId);
  const p = pricing(page);

  await calculate(page, "1 month");
  await expect(p.total).toHaveText("Total: 157.43 USD"); // 744 × 0.2116
  await editService(page, AWS_EU_WEST_1, { quantity: "12" });
  await calculate(page, "1 year");
  // New: 12 × 365 × 0.2116 = 926.808. Previous (24 h/day) yearly in eu-west-1: 1,853.616.
  // Priced in us-east-1, as v0.0.2 did, the SKU isn't found and the change would read +926.81.
  await expect(p.total).toHaveText("Total: 926.81 USD");
  await expect(p.priceChange).toHaveText("Price Change: -926.81");
});

/** Rewrites this architecture's stored baseline and result the way v0.0.2 stored them: no
 * `version`, and no `region` or `provider_options` on the baseline's selections, and no
 * `provider_options` on the result's priced contents. Then reloads. */
async function makeStoredCalculationLegacy(page: Page, architectureId: string) {
  await page.evaluate((id) => {
    const priorKey = `cloud-pricing-prior-calculation-${id}`;
    const prior = JSON.parse(localStorage.getItem(priorKey)!);
    delete prior.version;
    for (const s of prior.selections) {
      delete s.region;
      delete s.provider_options;
    }
    localStorage.setItem(priorKey, JSON.stringify(prior));

    const resultKey = `cloud-pricing-result-${id}`;
    const result = JSON.parse(localStorage.getItem(resultKey)!);
    for (const e of result.pricedContents) delete e.provider_options;
    localStorage.setItem(resultKey, JSON.stringify(result));
  }, architectureId);
  await page.reload();
  await expect(page.getByRole("button", { name: "Calculate" })).toBeVisible();
}

test("B1–B4: a GCP calculation stored by v0.0.2", async ({ page }) => {
  const api = new Api();
  const { architectureId } = await api.architecture("gcp", "us-east1", [
    { ...GCP.n2Core, provider_options: gcpMachine(2, 8) },
  ]);
  await openArchitecture(page, api, architectureId);
  const p = pricing(page);

  await calculate(page, "1 month");
  await editService(page, GCP.n2Core, { vcpus: 4 });
  await calculate(page);
  await expect(p.priceChange).toHaveText("Price Change: +47.04");

  await makeStoredCalculationLegacy(page, architectureId);

  // B2: no change → Price Change kept, no "updated" notice (also before calculating).
  await expect(p.priceChange).toHaveText("Price Change: +47.04");
  await expect(p.outOfDate).toHaveCount(0);
  await calculate(page);
  await expect(p.priceChange).toHaveText("Price Change: +47.04");
  await expect(p.outOfDate).toHaveCount(0);

  // B3: Duration switch → "Not available", no figure.
  await calculate(page, "1 year");
  await expect(p.total).toHaveText("Total: 1,404.58 USD"); // (4 × 0.031611 + 8 × 0.004237) × 8760
  await expect(p.unavailable).toBeVisible();
  await expect(p.priceChange).toHaveCount(0);

  // The "Not available" note survives a reload (it is stored with the result).
  await page.reload();
  await expect(p.unavailable).toBeVisible();

  // B4: switching back gives a real figure: a version 2 baseline was stored at B3, and its
  // contents (unchanged) re-priced monthly equal the new monthly total.
  await calculate(page, "1 month");
  await expect(p.total).toHaveText("Total: 119.29 USD");
  await expect(p.priceChange).toHaveText("Price Change: 0.00");
  const stored = await page.evaluate(
    (id) => JSON.parse(localStorage.getItem(`cloud-pricing-prior-calculation-${id}`)!).version,
    architectureId,
  );
  expect(stored).toBe(2);
});

test("B5: an AWS calculation stored by v0.0.2 is still re-priced after a Duration switch", async ({
  page,
}) => {
  const api = new Api();
  const { architectureId } = await api.architecture("aws", "eu-west-1", [AWS_EU_WEST_1]);
  await openArchitecture(page, api, architectureId);
  const p = pricing(page);

  await calculate(page, "1 month");
  await makeStoredCalculationLegacy(page, architectureId);
  await calculate(page, "1 year");
  await expect(p.unavailable).toHaveCount(0);
  await expect(p.priceChange).toBeVisible();
});
