import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * The desktop build, end to end: the sidecar serving the built client.
 *
 * A config of its own rather than a fourth project in `playwright.config.ts`,
 * because `webServer` is per config and this one is different in kind. There
 * is no Vite: the server serves `dist/` itself at `/`, which is exactly how the
 * Electron shell loads it. And the server is `commanderblitz.server.desktop`, started
 * the way the shell starts it -- `--generated-dir` pointed at a scratch
 * directory, `--remote-origin` pointed at the stub site, and the two test
 * switches (`COMMANDERBLITZ_FIXTURE_DECKS`, `COMMANDERBLITZ_CPU`) deliberately absent,
 * because a shipped build never sets them.
 *
 * The site is `tests/server/stub_site.py`: the real hosted app with Moxfield
 * answered from a fixture, started switched OFF. Every spec but one sees a
 * site that is down; the import spec switches it on, imports through it, and
 * switches it off again before it plays.
 *
 * What it proves is in `e2e/sidecar.spec.ts`: a page that makes no request off
 * the machine can deal a pod and play it, the door says what it cannot do, and
 * a deck imported through the site plays a whole game once the site is gone.
 */

const VENV_PYTHON =
  process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";
const PYTHON =
  process.env.PYTHON ?? (existsSync(resolve("..", VENV_PYTHON)) ? VENV_PYTHON : "python");

const SLOW = Number(process.env.E2E_SLOW ?? 1);

/** A Steam Deck's panel. */
const PORT = 8010;

/** The stub site, the sidecar's `--remote-origin`. */
const SITE_PORT = 8011;

/**
 * Fresh per run: nothing an earlier run imported or cached may leak in.
 *
 * Only in the process that starts the server. Playwright evaluates this file
 * again in every worker, and each evaluation used to leave an empty scratch
 * directory behind; the workers never read this value.
 */
const GENERATED =
  process.env.TEST_WORKER_INDEX === undefined
    ? mkdtempSync(join(tmpdir(), "commanderblitz-e2e-"))
    : "unused-in-a-worker";
const SITE_GENERATED =
  process.env.TEST_WORKER_INDEX === undefined
    ? mkdtempSync(join(tmpdir(), "commanderblitz-e2e-site-"))
    : "unused-in-a-worker";

/**
 * The server's environment: inherited, minus the switches a shipped build
 * never has, plus a proxy that answers nobody.
 *
 * THE PROXY IS WHAT MAKES THE SERVER OFFLINE. The spec aborts every request
 * the *browser* would send off the machine, but the lazy art fill and the
 * Moxfield import run in the server, and `urllib` honours these variables --
 * so a precon's chosen printing that is not in `data/art` fails to fetch and
 * falls back to the card's own art, exactly as it would on a Deck with no
 * connection. On the server only: a browser that read them could not reach
 * the sidecar either. `127.0.0.1` is exempt, because that is where the stub
 * site is, and the stub's own switch decides whether it answers.
 */
const env: Record<string, string> = {};
for (const [key, value] of Object.entries(process.env)) {
  if (
    value !== undefined &&
    key !== "COMMANDERBLITZ_FIXTURE_DECKS" &&
    key !== "COMMANDERBLITZ_CPU"
  ) {
    env[key] = value;
  }
}
env.HTTP_PROXY = "http://127.0.0.1:1";
env.HTTPS_PROXY = "http://127.0.0.1:1";
env.http_proxy = env.HTTP_PROXY;
env.https_proxy = env.HTTPS_PROXY;
env.NO_PROXY = "127.0.0.1,localhost";
env.no_proxy = env.NO_PROXY;

export default defineConfig({
  testDir: "./e2e",
  testMatch: /sidecar\.spec\.ts/,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  timeout: 120_000 * SLOW,
  expect: { timeout: 15_000 * SLOW },
  reporter: [["list"], ["html", { open: "never", outputFolder: "e2e-report" }]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "sidecar",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
  ],
  webServer: [
    {
      command:
        `"${PYTHON}" -m tests.server.stub_site --port ${SITE_PORT}` +
        ` --generated-dir "${SITE_GENERATED}" --offline`,
      cwd: "..",
      url: `http://127.0.0.1:${SITE_PORT}/__stub/stats`,
      env,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command:
        `"${PYTHON}" -m commanderblitz.server.desktop --port ${PORT}` +
        ` --client-dir frontend/dist --generated-dir "${GENERATED}"` +
        ` --remote-origin http://127.0.0.1:${SITE_PORT} --content-version e2e`,
      cwd: "..",
      url: `http://127.0.0.1:${PORT}/health`,
      env,
      // Never reused: the whole point is the server this config starts.
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
