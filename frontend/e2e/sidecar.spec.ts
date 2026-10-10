/**
 * The desktop build, offline.
 *
 * The server is `automtg.server.desktop` serving the built client, started by
 * `playwright.sidecar.config.ts` the way the Electron shell starts it, with the
 * hosted origin pointed at a port nobody answers. Every request that would
 * leave the machine is aborted at the browser, so a pass here means the game
 * dealt and played on what is on the device and nothing else.
 */

import { expect, test } from "@playwright/test";
import {
  budget,
  keepOpeningHand,
  openCatalog,
  setInstant,
  startGame,
  takeAction,
} from "./helpers";

const LOCAL = /^https?:\/\/127\.0\.0\.1:8010\//;

test.beforeEach(async ({ context }) => {
  // Anything not the sidecar is the outside world, and the outside world is
  // unreachable. A request that gets this far is a bug the spec should fail on.
  await context.route(/.*/, (route) => {
    if (LOCAL.test(route.request().url())) return route.continue();
    return route.abort("failed");
  });
});

test("the server serves the client itself, with no Vite in front", async ({ page }) => {
  const response = await page.goto("/");
  expect(response?.url()).toMatch(LOCAL);
  await expect(page).toHaveTitle(/Commander Blitz/);
  await expect(page.getByTestId("home")).toBeVisible();
});

test("the config says desktop, offline, and which content it is", async ({ request }) => {
  const config = await (await request.get("/api/config")).json();
  expect(config).toEqual({
    mode: "desktop",
    online: false,
    remote_origin: "http://127.0.0.1:1",
    app_version: expect.any(String),
    content_version: "e2e",
  });
});

test("the door greys what needs a connection, and says so", async ({ page }) => {
  await setInstant(page);
  await page.goto("/");
  const online = page.getByTestId("join-pod");
  await expect(online).toHaveText(/Online/);
  await expect(online).toHaveAttribute("aria-disabled", "true");

  // One click selects the card, the second presses it. `force`: the card is
  // `aria-disabled` so the ring and a screen reader know, but it is a real
  // button a player can press -- that is how it gets to say why -- and
  // Playwright's actionability check would otherwise wait on it forever.
  await online.click({ force: true });
  await online.click({ force: true });
  await expect(page.getByTestId("offline-note")).toBeVisible();
  await expect(page.getByTestId("join-hold")).toHaveCount(0);
});

test("the catalogue's import strip is disabled, and the lobby has no Invite", async ({
  page,
}) => {
  await openCatalog(page);
  await expect(page.getByTestId("import-offline")).toBeVisible();
  await expect(page.getByTestId("import-go")).toBeDisabled();
  await expect(page.getByTestId("import-url")).toBeDisabled();
  // Back to the lobby bar: nobody can reach a server on 127.0.0.1.
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("deck-catalog")).toBeHidden();
  await expect(page.getByTestId("leave-pod")).toBeVisible();
  await expect(page.getByTestId("invite")).toHaveCount(0);
});

test("a solo pod deals and plays with nothing off the device", async ({ page, request }) => {
  test.setTimeout(budget(300_000));
  const before = await (await request.get("/health")).json();

  await startGame(page, { deck: "aesi_tyrant_of_gyre_strait", opponents: 1, seed: 7 });
  await keepOpeningHand(page);
  for (let i = 0; i < 5; i += 1) {
    if ((await takeAction(page)) === null) break;
  }
  await expect(page.getByTestId("stall-toast")).toHaveCount(0);

  const after = await (await request.get("/health")).json();
  expect(after.games).toBe(before.games + 1);
  // Precon art is committed and ships with the build, so nothing was fetched:
  // the cache is exactly what it was before the game.
  expect(after.art.cached).toBe(before.art.cached);
});
