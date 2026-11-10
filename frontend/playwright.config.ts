import { defineConfig, devices } from "@playwright/test";

// End-to-end tests (020 onwards): the real app in headless Chromium, against its own backend,
// database and the committed pricing fixture (e2e/start-backend.sh). Ports differ from the dev
// servers' (8000, 5173) so a running dev setup is left alone.
const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8100);
const FRONTEND_PORT = Number(process.env.E2E_FRONTEND_PORT ?? 5199);
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`;
const FRONTEND_URL = `http://localhost:${FRONTEND_PORT}`;

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  // Each test makes its own user and architectures, so tests can run in parallel safely.
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  expect: { timeout: 10_000 },
  use: {
    baseURL: FRONTEND_URL,
    viewport: { width: 1600, height: 1000 },
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1600, height: 1000 } },
    },
  ],
  webServer: [
    {
      command: "bash e2e/start-backend.sh",
      url: `${BACKEND_URL}/health`,
      env: { E2E_BACKEND_PORT: String(BACKEND_PORT) },
      timeout: 120_000,
      reuseExistingServer: false,
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      command: `npx vite --port ${FRONTEND_PORT} --strictPort`,
      url: FRONTEND_URL,
      env: { API_PROXY_TARGET: BACKEND_URL },
      timeout: 60_000,
      reuseExistingServer: false,
    },
  ],
});
