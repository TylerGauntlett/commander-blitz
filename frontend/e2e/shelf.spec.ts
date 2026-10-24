/**
 * The shelf's segments against a real engine (ADR 0024).
 *
 * The server ships the favorites; the precons and the imports are appended to
 * its list by `stubDeckList`, because no precon is shipped yet and an import
 * would reach Moxfield. What is under test is the screen: which segment holds
 * what, the precons' runs and their order, and that a star is drawn from the
 * server's answer rather than from the press.
 */

import { expect, type Page, test } from "@playwright/test";
import { browseDecks, STUB_IMPORTS, STUB_PRECONS, setInstant, stubDeckList } from "./helpers";

/** The deck ids of the tiles on the shelf, in the order they are drawn. */
async function tileIds(page: Page): Promise<string[]> {
  const ids = await page
    .locator(".shelf__body .tile")
    .evaluateAll((tiles) => tiles.map((tile) => tile.getAttribute("data-testid") ?? ""));
  return ids.map((id) => id.replace(/^deck-/, ""));
}

/** The named runs on the shelf, in order. */
function regions(page: Page) {
  return page.getByTestId("deck-catalog").locator('.shelf__body [role="region"]');
}

test.describe("the shelf's segments", () => {
  test.beforeEach(async ({ page }) => {
    await setInstant(page);
  });

  test("are All, Precons, Favorites and Yours", async ({ page }) => {
    await browseDecks(page);
    await expect(page.locator(".shelf .seg__b")).toHaveText([
      "All",
      "Precons",
      "Favorites",
      "Yours",
    ]);
  });

  test("Favorites holds the shipped decks and nothing else", async ({ page }) => {
    const shipped = (await (await page.request.get("/api/decks")).json()) as {
      id: string;
      source: string;
    }[];
    const favorites = shipped
      .filter((deck) => deck.source === "favorite")
      .map((deck) => deck.id);
    expect(favorites, "the server ships favorites").toContain("aesi_tyrant_of_gyre_strait");
    expect(favorites).toContain("edgar_markov");

    await stubDeckList(page, [...STUB_PRECONS, ...STUB_IMPORTS]);
    await browseDecks(page);
    await page.getByTestId("source-favorite").click();

    await expect(page.locator(".shelf__body .tile")).toHaveCount(favorites.length);
    expect(new Set(await tileIds(page))).toEqual(new Set(favorites));
    // One run under its own segment: the button above already names it.
    await expect(regions(page)).toHaveCount(0);
  });

  test("Precons run by release, newest first, each a named region", async ({ page }) => {
    await stubDeckList(page, STUB_PRECONS);
    await browseDecks(page);
    await page.getByTestId("source-precon").click();

    const named = regions(page);
    await expect(named.first()).toHaveAttribute("aria-label", "Foundations Commander");
    await expect(named.nth(1)).toHaveAttribute("aria-label", "Duskmourn Commander");
    await expect(named.first().getByRole("heading")).toHaveText("Foundations Commander");
    await expect(named.first().getByTestId("deck-fdc_stub_angels")).toBeVisible();
    await expect(named.nth(1).getByTestId("deck-dsc_stub_older")).toBeVisible();

    // The precons name archetypes, so the shelf offers the filter, and a press
    // narrows the runs to the decks that play that way.
    const archetype = page.getByTestId("deck-archetype");
    await expect(archetype).toHaveAttribute("aria-label", "Archetype: Any");
    await archetype.click();
    await expect(archetype).toHaveAttribute("aria-label", "Archetype: Punisher");
    await expect(named.first()).toHaveAttribute("aria-label", "Duskmourn Commander");
    await expect(page.getByTestId("deck-fdc_stub_angels")).toHaveCount(0);
  });

  test("the archetype filter is not drawn when no deck names one", async ({ page }) => {
    await browseDecks(page);
    await expect(page.locator(".shelf__body .tile").first()).toBeVisible();
    await expect(page.getByTestId("deck-archetype")).toHaveCount(0);
  });

  test("a star pins an import to the top of Yours, from the server's answer", async ({
    page,
  }) => {
    await stubDeckList(page, STUB_IMPORTS);
    const [, zeta] = STUB_IMPORTS;
    let sent: unknown = null;
    await page.route(`**/api/decks/${zeta.id}/star`, (route) => {
      sent = route.request().postDataJSON();
      return route.fulfill({ json: { ...zeta, starred: true } });
    });

    await browseDecks(page);
    await page.getByTestId("source-moxfield").click();
    await expect.poll(() => tileIds(page)).toEqual(["mox_stub_alpha", "mox_stub_zeta"]);

    const star = page.getByTestId(`deck-${zeta.id}-star`);
    await expect(star).toHaveAttribute("aria-pressed", "false");
    await star.click();

    await expect(star).toHaveAttribute("aria-pressed", "true");
    expect(sent).toEqual({ starred: true });
    await expect.poll(() => tileIds(page)).toEqual(["mox_stub_zeta", "mox_stub_alpha"]);
  });
});
