/**
 * The desktop build, offline.
 *
 * The server is `commanderblitz.server.desktop` serving the built client, started by
 * `playwright.sidecar.config.ts` the way the Electron shell starts it, with the
 * hosted origin pointed at the stub site, switched off. Every request that
 * would leave the machine is aborted at the browser, so a pass here means the
 * game dealt and played on what is on the device and nothing else.
 */

import { expect, test } from "@playwright/test";
import {
  budget,
  isOver,
  keepOpeningHand,
  openCatalog,
  setInstant,
  startGame,
  takeAction,
  waitForOurTurn,
} from "./helpers";

const LOCAL = /^https?:\/\/127\.0\.0\.1:8010\//;

/** The stub site: the sidecar's hosted origin, reached by the test, never the page. */
const SITE = "http://127.0.0.1:8011";

/** The deck `tests/server/stub_site.py` answers for any Moxfield link. */
const DECK_URL = "https://moxfield.com/decks/vVdybWVgC0imBOlW63FlTg";

test.beforeEach(async ({ context, request }) => {
  // The site is down unless a spec says otherwise, and says so itself.
  await request.post(`${SITE}/__stub/state`, { data: { online: false } });
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
    remote_origin: SITE,
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

/*
 * Last in the file, deliberately: it switches the site on, and the sidecar
 * trusts a probe answer for half a minute, so a spec after it could see the
 * door lit for a site that has already gone again.
 */
test("a deck imported through the site plays a whole game once the site is gone", async ({
  page,
  request,
}) => {
  test.slow();
  test.setTimeout(budget(900_000));

  // Online: the import goes through the site and lands whole (ADR 0022).
  await request.post(`${SITE}/__stub/state`, { data: { online: true } });
  const response = await request.post("/api/decks/import", {
    data: { url: DECK_URL },
    timeout: budget(240_000),
  });
  expect(response.status()).toBe(201);
  const imported = await response.json();
  expect(imported.art_prefetch.complete).toBe(true);
  expect(imported.art_prefetch.missing).toEqual([]);
  expect(imported.deck.complete).toBe(true);

  // Offline: nothing the game draws may need the site again.
  await request.post(`${SITE}/__stub/state`, { data: { online: false } });
  // Every illustration the deck needed, by the name the site serves it under.
  const fetched: string[] = (await (await request.get(`${SITE}/__stub/stats`)).json()).art;
  expect(fetched.length).toBeGreaterThan(0);

  await startGame(page, { deck: imported.deck.id, opponents: 1, seed: 11 });
  let steps = 0;
  for (; steps < 3000; steps += 1) {
    await waitForOurTurn(page);
    if (await isOver(page)) break;
    await takeAction(page, ["keep", "play_land", "cast", "add_attacker", "pass"]);
  }
  expect(await isOver(page), `game never finished in ${steps} decisions`).toBe(true);
  await expect(page.getByTestId("game-over")).toBeVisible();

  // The opponent's precon may go looking for a printing the device never had;
  // the imported deck must not have gone looking for anything.
  const asked: string[] = (await (await request.get(`${SITE}/__stub/stats`)).json()).offline_art;
  expect(asked.filter((name) => fetched.includes(name))).toEqual([]);
});
