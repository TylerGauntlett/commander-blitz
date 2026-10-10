import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig, devices } from "@playwright/test";

/** The repo's virtualenv interpreter, by platform. */
const VENV_PYTHON =
  process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";

/**
 * The interpreter that boots uvicorn, in order of preference: `PYTHON` from the
 * environment (`scripts/verify.py` sets it to its own `sys.executable`), the
 * repo's virtualenv when it exists, else whatever `python` is on PATH. CI has no
 * `.venv` -- `setup-python` installs into the runner's interpreter -- so the
 * hard-coded venv path meant the web server could never start there.
 */
const PYTHON =
  process.env.PYTHON ?? (existsSync(resolve("..", VENV_PYTHON)) ? VENV_PYTHON : "python");

/**
 * End-to-end against the real engine.
 *
 * Both processes are booted here so a spec run needs no setup: uvicorn on 8000
 * and vite on 5173, with vite proxying /api through. `reuseExistingServer` means
 * a dev session already running is used as-is rather than fought over.
 */
/**
 * Every budget in the suite, scaled once.
 *
 * The same unchanged commit produced three different timeout failures across
 * two runs, and no two runs agreed on which test (TECH_DEBT FT-06). Each one
 * passed alone on a quiet machine: the trigger was load, not code. Raising the
 * numbers in place would hide a real slowdown, so the numbers stay and the
 * *multiplier* is the knob -- `scripts/verify.py --e2e` sets `E2E_SLOW=2`
 * because it runs this suite after two Storybook browsers on the same box.
 * `helpers.budget()` applies the same factor to every per-test budget.
 */
const SLOW = Number(process.env.E2E_SLOW ?? 1);

export default defineConfig({
  testDir: "./e2e",
  // The engine is deterministic per seed, but the AI pump is a real timing loop;
  // one retry absorbs a slow cold start without hiding a genuine failure.
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  timeout: 120_000 * SLOW,
  expect: { timeout: 15_000 * SLOW },
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
      // another. `sidecar` has a config of its own (`playwright.sidecar.config.ts`):
      // it needs a different server, and `webServer` is per config.
      testIgnore: /(handheld|pad|deckfit|sidecar)\.spec\.ts/,
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
      // Quoted: a `sys.executable` handed in from `verify.py` is absolute, and
      // this checkout's path has a space in it.
      command: `"${PYTHON}" -m uvicorn commanderblitz.server.app:get_app --factory --port 8000`,
      cwd: "..",
      url: "http://127.0.0.1:8000/health",
      // The seeded specs were written against the retired first Edgar and Aesi
      // lists and the pre-strategy CPU. Both come back only on request; a dev
      // server you reuse needs the same two variables (docs/testing.md).
      env: { COMMANDERBLITZ_FIXTURE_DECKS: "1", COMMANDERBLITZ_CPU: "classic" },
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
