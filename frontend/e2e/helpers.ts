/**
 * Shared helpers for the end-to-end tests: build architectures through the API (fast, exact),
 * then drive the page the way a user does.
 *
 * Identity: the app's bearer token is a user id kept in localStorage, and the backend creates
 * the user on first use. Each test makes a fresh id, so tests never see each other's data.
 * Item keys and prices come from the fixture READMEs in
 * backend/tests/fixtures/pricing_parquet/{aws,gcp,azure}/README.md.
 */
import { randomUUID } from "node:crypto";

import { expect, type Locator, type Page } from "@playwright/test";

const BACKEND_URL = `http://localhost:${process.env.E2E_BACKEND_PORT ?? 8100}`;

export type Provider = "aws" | "gcp" | "azure";

export const GCP = {
  n2Core: { service_code: "6F81-5844-456A", sku: "BB77-5FDA-69D9" },
  n2Ram: "5B01-D157-A097",
  balancedPd: { service_code: "6F81-5844-456A", sku: "6AE1-525F-8B80" },
  storage: { service_code: "95FF-2EF5-5EA1", sku: "E5F0-6A5D-7BAD" },
  sqlCpu: { service_code: "9662-B51E-5089", sku: "965E-7C36-08E6" },
};

export const AZURE = {
  vm: {
    service_code: "DZH313Z7MMC8",
    sku: "DZH318Z08M9W/004T/db8c0962-f3f8-5b44-99aa-f3c7c1e668c8",
  },
  diskP10: {
    service_code: "DZH317F1HKN0",
    sku: "DZH318Z0BP04/0035/93a6a529-4f49-47cb-9b1e-db9e5f23263f",
  },
  egress: {
    service_code: "DZH318FHKQ5W",
    sku: "DZH318Z0BNVX/001D/9995d93a-7d35-4d3f-9c69-7a7fea447ef4",
  },
};

/** EC2 on demand in eu-west-1, $0.2116 an hour; not in us-east-1. */
export const AWS_EU_WEST_1 = { service_code: "AmazonEC2", sku: "22857BA35WWDDHD7" };

export function gcpMachine(vcpus: number, memoryGib: number) {
  return {
    kind: "gcp_machine",
    version: 1,
    vcpus,
    memory_gib: String(memoryGib),
    ram_sku: GCP.n2Ram,
  };
}

export function azureVm(os: "linux" | "windows") {
  return { kind: "azure_vm", version: 1, os };
}

export interface SelectionSpec {
  service_code: string;
  sku: string;
  usage_quantity?: string;
  provider_options?: Record<string, unknown>;
}

export class Api {
  constructor(readonly userId: string = randomUUID()) {}

  async call<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${BACKEND_URL}/api/v1${path}`, {
      method,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${this.userId}` },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    if (!res.ok) throw new Error(`${method} ${path} → ${res.status}: ${text}`);
    return (text ? JSON.parse(text) : undefined) as T;
  }

  /** One architecture with one box in `region` holding `selections`; returns the ids. */
  async architecture(
    provider: Provider,
    region: string,
    selections: SelectionSpec[],
    name = `E2E ${provider}`,
  ): Promise<{ architectureId: string; collectionId: string; selectionIds: string[] }> {
    const arch = await this.call<{ id: string }>("POST", "/architectures", { name, provider });
    const coll = await this.call<{ id: string }>("POST", `/architectures/${arch.id}/collections`, {
      type: "application_component",
      name: "App",
      region,
    });
    const selectionIds: string[] = [];
    for (const s of selections) {
      const created = await this.call<{ id: string }>(
        "POST",
        `/collections/${coll.id}/sku-selections`,
        {
          service_code: s.service_code,
          sku: s.sku,
          pricing_term: "on_demand",
          purchase_option: "not_applicable",
          usage_quantity: s.usage_quantity ?? "24",
          ...(s.provider_options ? { provider_options: s.provider_options } : {}),
        },
      );
      selectionIds.push(created.id);
    }
    return { architectureId: arch.id, collectionId: coll.id, selectionIds };
  }
}

/** The Admin account a fresh database is seeded with (migration 0004). */
export async function adminApi(): Promise<Api> {
  const res = await fetch(`${BACKEND_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "Admin", password: "admin123" }),
  });
  if (!res.ok) throw new Error(`Admin login → ${res.status}: ${await res.text()}`);
  return new Api(((await res.json()) as { id: string }).id);
}

/** Opens an architecture in the workspace as `api`'s user. */
export async function openArchitecture(page: Page, api: Api, architectureId: string) {
  await page.addInitScript((id) => {
    localStorage.setItem("cloud-pricing-guest-id", id);
    localStorage.setItem("cloud-pricing-current-identity-id", id);
  }, api.userId);
  await page.goto(`/architectures/${architectureId}`);
  await settled(page);
}

/** Waits until no calculation is running (the Calculate button is disabled while one is, up to
 * and including the Price Change re-pricing), then for React to commit. An architecture with
 * services and no stored result calculates by itself when opened (FR-017). */
async function settled(page: Page) {
  await expect(page.getByRole("button", { name: "Calculate" })).toBeEnabled();
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => r(null))));
}

/** A service's icon button on the main canvas (its accessible name starts with the code and SKU). */
export function serviceButton(scope: Page | Locator, s: { service_code: string; sku: string }) {
  return scope.getByRole("button", {
    name: new RegExp(`^${escape(s.service_code)}, Sku: ${escape(s.sku)}`),
  });
}

function escape(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function pricing(page: Page) {
  const result = page.getByRole("region", { name: "Calculation result" });
  return {
    result,
    total: result.getByRole("heading", { name: /^Total:/ }),
    priceChange: result.getByText(/^Price Change:/),
    unavailable: result.getByText(
      "Not available: previous calculation from prior version is unreliable",
    ),
    outOfDate: page.getByText("Architecture has been updated since last pricing"),
  };
}

/** Calculate at `duration` and wait for the new total. */
export async function calculate(page: Page, duration?: "1 day" | "1 month" | "1 year") {
  if (duration) await page.getByLabel("Duration").selectOption({ label: duration });
  const calculated = page.waitForResponse(
    (r) => /\/architectures\/[^/]+\/calculate/.test(r.url()) && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Calculate" }).click();
  expect((await calculated).ok()).toBe(true);
  // A Price Change after a Duration switch needs the snapshot re-pricing too.
  await settled(page);
  await expect(pricing(page).total).toBeVisible();
}

/** Selects a service on the canvas, edits its fields, and saves. */
export async function editService(
  page: Page,
  s: { service_code: string; sku: string },
  fields: { vcpus?: number; memoryGib?: number; os?: "linux" | "windows"; quantity?: string },
) {
  await serviceButton(page, s).click();
  if (fields.vcpus !== undefined) await page.getByLabel("vCPUs").fill(String(fields.vcpus));
  if (fields.memoryGib !== undefined) {
    await page.getByLabel("Memory (GiB)").fill(String(fields.memoryGib));
  }
  if (fields.os) await page.getByLabel("Operating system").selectOption(fields.os);
  if (fields.quantity !== undefined) {
    await page.getByLabel(/^(Usage quantity|Hours per day)/).fill(fields.quantity);
  }
  const saved = page.waitForResponse(
    (r) => /\/sku-selections\/[^/]+$/.test(r.url()) && r.request().method() === "PATCH",
  );
  // A save reloads the architecture; Calculate captures its contents from that reload, so a
  // click before it lands would price the new contents against the old ones.
  const reloaded = page.waitForResponse(
    (r) => /\/architectures\/[^/]+$/.test(r.url()) && r.request().method() === "GET",
  );
  await page.getByRole("button", { name: "Save" }).click();
  expect((await saved).ok()).toBe(true);
  expect((await reloaded).ok()).toBe(true);
  await settled(page);
}

/** Turns the page's dark theme on or off (the `.dark` class on <html>, as the app's CSS expects). */
export async function setDarkTheme(page: Page, dark: boolean) {
  await page.evaluate((on) => document.documentElement.classList.toggle("dark", on), dark);
}

/** The main canvas (the pop-out dialog has its own). */
export function mainCanvas(page: Page): Locator {
  return page.locator(".react-flow").first();
}

/** "<icon folder>/<file stem>" of the first image a service button shows, e.g.
 * "gcp-icons/Compute-Engine" or "providers/gcp_icon" (a fallback tile's logo). */
export async function iconOf(button: Locator): Promise<string> {
  const src = await button.locator("img").first().getAttribute("src");
  // The dev server serves assets under their own names (no content hash).
  const match = decodeURIComponent(src ?? "").match(/([^/]+)\/([^/]+?)\.(svg|png)/);
  return match ? `${match[1]}/${match[2]}` : `unknown:${src}`;
}

/** Every service button's icon on a canvas, in document order. */
export async function canvasIcons(canvas: Locator): Promise<string[]> {
  const buttons = await canvas.locator("button[aria-pressed]").all();
  return Promise.all(buttons.map(iconOf));
}

/** Every image on the canvas has loaded and has a size (a missing file would be 0 × 0). */
export async function expectImagesLoaded(canvas: Locator) {
  await expect
    .poll(() =>
      canvas
        .locator("button[aria-pressed] img")
        .evaluateAll((imgs) =>
          imgs
            .filter((i) => getComputedStyle(i).display !== "none")
            .every(
              (i) => (i as HTMLImageElement).complete && (i as HTMLImageElement).naturalWidth > 0,
            ),
        ),
    )
    .toBe(true);
}

/** Rewrites one selection in the architecture the page loads (not on the server), for UI
 * states the fixture data has no example of, such as a GCP service without an icon. */
export async function patchArchitectureResponse(
  page: Page,
  architectureId: string,
  patches: Record<string, Record<string, unknown>>,
) {
  await page.route(`**/api/v1/architectures/${architectureId}`, async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const response = await route.fetch();
    const body = await response.json();
    for (const collection of body.collections) {
      for (const s of collection.sku_selections) Object.assign(s, patches[s.id] ?? {});
    }
    await route.fulfill({ response, json: body });
  });
}
