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
    /*
     * The desktop suite, unchanged.
     *
     * `testIgnore` rather than moving files: the handheld specs live in the same
     * directory and share `helpers.ts`, and the one thing this project must keep
     * proving is that the wide board still behaves exactly as it did. Running
     * the handheld specs here at 1600x950 would test the desktop layout while
     * claiming to test the compact one.
     */
    {
      name: "chromium",
      // `\.spec\.` on both sides: a bare /handheld/ also matches
      // `handheldAssert.ts`, and Playwright refuses to let one test file import
      // another.
      testIgnore: /(handheld|pad|deckfit)\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1600, height: 950 } },
    },
    /*
     * A Steam Deck's panel, exactly.
     *
     * A second project rather than a second viewport on the first, so the
     * desktop numbers every existing spec asserts are never moved -- the whole
     * safety argument of this change is that the wide board is untouched, and it
     * is worth nothing if the suite that proves it starts running somewhere else.
     */
    {
      name: "handheld",
      testMatch: /(handheld|pad)\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
    /*
     * The fit gate, which sets its own viewport per test.
     *
     * `deckfit.spec.ts` runs the same checks at 1200x800 and 1280x800, so it
     * declares the size with `test.use` rather than inheriting one -- the two
     * are not interchangeable. 1200 is the same height with ~36px less rail, and
     * more than one regression found while writing it showed up at exactly one
     * of the two widths.
     */
    {
      name: "deckfit",
      testMatch: /deckfit\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
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
