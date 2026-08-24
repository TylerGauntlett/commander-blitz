/**
 * The addresses, in a real browser.
 *
 * `pod.spec.ts` covers the pod's own address because that is where the two
 * browsers already are. This file covers the rest: the catalogue, the 404, and
 * the one thing worth running a whole browser to prove -- that reloading at the
 * table puts you back in your seat. Before the router that dropped you at the
 * front door mid-game, and no unit test can show a real page load doing it.
 */

import { expect, test } from "@playwright/test";
import { setInstant, startGame } from "./helpers";

test.describe("the catalogue is a place", () => {
  test("opens at its own address", async ({ page }) => {
    await setInstant(page);
    await page.goto("/decks");
    await page.getByTestId("deck-catalog").waitFor({ timeout: 15_000 });
  });

  test("a deck link opens the dossier over the catalogue", async ({ page }) => {
    await setInstant(page);
    await page.goto("/decks/aesi");
    // Both, because the dossier is a nested route rather than a screen of its
    // own -- which is what keeps the catalogue's filters alive underneath it.
    await page.getByTestId("deck-catalog").waitFor({ timeout: 15_000 });
    await page.getByTestId("deck-dossier").waitFor({ timeout: 15_000 });
  });

  test("browsing is what the back button is for", async ({ page }) => {
    await setInstant(page);
    await page.goto("/");
    await page.getByTestId("home").waitFor();
    // The footer link is a card now. `browse-decks` is one of the four test ids
    // the front door's redesign had to carry across, and it is what a suite
    // should be driving rather than a string of copy.
    await page.getByTestId("browse-decks").click();
    await expect(page).toHaveURL(/\/decks$/);
    await page.goBack();
    await expect(page).toHaveURL(/\/$/);
    await page.getByTestId("home").waitFor();
  });
});

test.describe("an address that is not anything", () => {
  test("says so, and offers the door", async ({ page }) => {
    await setInstant(page);
    await page.goto("/nonsense");
    await page.getByTestId("not-found").waitFor();
    await page.getByRole("link", { name: /front door/ }).click();
    await page.getByTestId("home").waitFor();
  });

  test("the singular is a typo, not an alias", async ({ page }) => {
    // One letter from a real invite link, and somebody will type it. Landing
    // them silently at the door looks like the invite was rejected.
    await setInstant(page);
    await page.goto("/pod/GYRE-8412");
    await page.getByTestId("not-found").waitFor();
  });
});

test.describe("reloading at the table", () => {
  test("comes back to the same seat", async ({ page }) => {
    await startGame(page, { opponents: 1, seed: 7 });
    const url = page.url();
    expect(url).toMatch(/\/games\/[^/]+$/);

    const before = await page
      .locator(".hand [data-card-name]")
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-card-name")));
    expect(before.length).toBeGreaterThan(0);

    // The token is in `sessionStorage`, keyed by pod code; the game id in the
    // URL finds its way there through the link this client wrote when it was
    // dealt. Nothing about identity is in the address itself.
    await page.reload();
    await page.getByTestId("table").waitFor({ timeout: 60_000 });
    await expect(page).toHaveURL(url);

    const after = await page
      .locator(".hand [data-card-name]")
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-card-name")));
    expect(after.sort()).toEqual(before.sort());
  });

  test("a table belonging to somebody else's pod is refused", async ({ browser }) => {
    const mine = await browser.newContext();
    const theirs = await browser.newContext();
    const page = await mine.newPage();
    await startGame(page, { opponents: 1, seed: 7 });
    const url = page.url();

    // A second context is a second `sessionStorage`, so this browser has no
    // record of the game and no token to send.
    const stranger = await theirs.newPage();
    await setInstant(stranger);
    await stranger.goto(url);
    await expect(stranger.getByText(/belongs to a pod you are not in/)).toBeVisible({
      timeout: 30_000,
    });

    await mine.close();
    await theirs.close();
  });
});
