import { defineConfig, devices } from "@playwright/test";

/** The repo's virtualenv interpreter, by platform. */
const PYTHON = process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";

/**
 * End-to-end against the real engine.
 *
 * Both processes are booted here so a spec run needs no setup: uvicorn on 8000
 * and vite on 5173, with vite proxying /api through. `reuseExistingServer` means
 * a dev session already running is used as-is rather than fought over.
 */
export default defineConfig({
  testDir: "./e2e",
  // The engine is deterministic per seed, but the AI pump is a real timing loop;
  // one retry absorbs a slow cold start without hiding a genuine failure.
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "e2e-report" }]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1600, height: 950 },
  },
  // The viewport must come *after* the device spread: `devices["Desktop Chrome"]`
  // carries its own 1280x720, and a project's `use` overrides the top-level one.
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1600, height: 950 } },
    },
  ],
  webServer: [
    {
      command: `${PYTHON} -m uvicorn automtg.server.app:get_app --factory --port 8000`,
      cwd: "..",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
