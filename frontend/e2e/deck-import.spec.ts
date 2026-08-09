import { expect, test } from "@playwright/test";

/**
 * The Moxfield import, driven through the DOM.
 *
 * `/api/decks/import` is stubbed in every case: an e2e run must never reach a
 * third party, both because it would be slow and flaky and because the whole
 * point of this architecture is that the browser only ever talks to our server.
 * What is being tested here is the *screen* -- that the coverage report is
 * honest and legible, and that every failure says something a person can act on.
 *
 * Per `mockups/flow/_flow.js`: "The error state matters more than the happy
 * path, because it is the state the real feature will spend its life in." So
 * that is most of this file.
 */

const DECK = {
  id: "mox_test",
  name: "Spiders",
  commanders: ["shelob_child_of_ungoliant"],
  commander_names: ["Shelob, Child of Ungoliant"],
  color_identity: ["B", "G"],
  card_count: 100,
  notes: "Imported from Moxfield (test).",
  source: "moxfield",
  playable: 26,
  simplified: 74,
};

const REPORT = {
  deck: DECK,
  source: "moxfield",
  source_id: "test",
  total: 100,
  playable: 26,
  simplified: 74,
  lands: 37,
  lands_producing_mana: 34,
  cards: [
    {
      name: "Shelob, Child of Ungoliant",
      qty: 1,
      card_id: "shelob_child_of_ungoliant",
      origin: "partial",
      notes: ["rules text not implemented: Other Spiders you control have deathtouch"],
    },
    { name: "Forest", qty: 16, card_id: "forest", origin: "native", notes: [] },
  ],
  problems: [],
};

/** Stub the import endpoint with a success, or with an error body. */
async function stubImport(
  page: import("@playwright/test").Page,
  response: { status: number; body: unknown },
) {
  await page.route("**/api/decks/import", (route) =>
    route.fulfill({
      status: response.status,
      contentType: "application/json",
      body: JSON.stringify(response.body),
    }),
  );
}

test.describe("importing a Moxfield deck", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("deck-import")).toBeVisible();
  });

  test("a link that is not Moxfield is rejected without a request", async ({ page }) => {
    let called = false;
    await page.route("**/api/decks/import", (route) => {
      called = true;
      return route.abort();
    });

    await page.getByTestId("import-url").fill("https://example.com/decks/abc");
    await page.getByTestId("import-go").click();

    await expect(page.getByTestId("import-error")).toHaveText(
      "That is not a Moxfield deck link.",
    );
    // The client-side guard is the point: an obviously wrong paste costs nothing.
    expect(called).toBe(false);
  });

  test("a private deck says how to fix it", async ({ page }) => {
    await stubImport(page, {
      status: 403,
      body: {
        detail: {
          detail: "That deck is private. Set it to public and try again.",
          code: "private",
        },
      },
    });

    await page.getByTestId("import-url").fill("https://moxfield.com/decks/abc123");
    await page.getByTestId("import-go").click();

    // "Private" and "missing" send somebody to two different places, so the two
    // must not collapse into one message.
    await expect(page.getByTestId("import-error")).toContainText("public");
  });

  test("a deck that does not exist says so", async ({ page }) => {
    await stubImport(page, {
      status: 404,
      body: { detail: { detail: "No deck with that link.", code: "not_found" } },
    });

    await page.getByTestId("import-url").fill("https://moxfield.com/decks/nope");
    await page.getByTestId("import-go").click();

    await expect(page.getByTestId("import-error")).toHaveText("No deck with that link.");
  });

  test("a list that is not 100 cards names the count", async ({ page }) => {
    await stubImport(page, {
      status: 422,
      body: {
        detail: {
          detail: "That list has 97 cards. A Commander deck has 100.",
          code: "bad_size",
        },
      },
    });

    await page.getByTestId("import-url").fill("https://moxfield.com/decks/abc123");
    await page.getByTestId("import-go").click();

    await expect(page.getByTestId("import-error")).toContainText("97");
  });

  test("the coverage report leads with what was simplified", async ({ page }) => {
    await stubImport(page, { status: 201, body: REPORT });

    await page.getByTestId("import-url").fill("https://moxfield.com/decks/abc123");
    await page.getByTestId("import-go").click();

    const report = page.getByTestId("import-coverage");
    await expect(report).toBeVisible();
    await expect(page.getByTestId("import-playable")).toHaveText("26 playable");
    await expect(page.getByTestId("import-simplified")).toHaveText("74 simplified");

    // A deck that looks like 37 lands and behaves like 34 is the single most
    // confusing thing an import can produce, so it gets its own line.
    await expect(page.getByTestId("import-mana")).toContainText("3");
  });

  test("each simplified card can be expanded to see what changed", async ({ page }) => {
    await stubImport(page, { status: 201, body: REPORT });

    await page.getByTestId("import-url").fill("https://moxfield.com/decks/abc123");
    await page.getByTestId("import-go").click();

    // Collapsed by default: 74 cards of notes would bury the Play button.
    await expect(page.getByTestId("import-toggle")).toBeVisible();
    await page.getByTestId("import-toggle").click();
    await expect(page.getByText("Shelob, Child of Ungoliant")).toBeVisible();
    await expect(page.getByText(/rules text not implemented/)).toBeVisible();
  });

  test("the imported deck joins the grid and is selected", async ({ page }) => {
    await stubImport(page, { status: 201, body: REPORT });
    // The refetch after an import has to see the new deck.
    await page.route("**/api/decks", async (route) => {
      const response = await route.fetch();
      const decks = await response.json();
      return route.fulfill({ json: [...decks, DECK] });
    });

    await page.getByTestId("import-url").fill("https://moxfield.com/decks/abc123");
    await page.getByTestId("import-go").click();

    const tile = page.getByTestId(`deck-${DECK.id}`);
    await expect(tile).toBeVisible();
    // Selected, because somebody who pasted a link wants to play that deck.
    await expect(tile).toHaveClass(/deck--on/);
    await expect(tile).toContainText("Yours");
    // The honesty requirement, on the tile itself and not only in the dialog.
    await expect(page.getByTestId(`deck-${DECK.id}-simplified`)).toContainText("74");
  });

  test("a precon tile carries no simplified count", async ({ page }) => {
    // An always-present "0 simplified" would train people to stop reading the
    // line that matters.
    await expect(page.getByTestId("deck-aesi")).toBeVisible();
    await expect(page.getByTestId("deck-aesi-simplified")).toHaveCount(0);
  });
});
