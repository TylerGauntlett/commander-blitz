/**
 * Can you read a card that is a full-bleed illustration?
 *
 * `tests/palette.test.ts` reads `cards.css` off disk, which is the right place
 * to guard a number but cannot see an override landing from `theme.css`, a media
 * query, or an inline style. These read the *resolved* values off real elements
 * in a real browser, which is the only way to know what actually shipped.
 *
 * The card's text sits on graded scrims over an illustration nobody chose, so
 * the two numbers that decide whether it reads -- how dark the scrims are and
 * how thick the frame is -- are worth measuring on the rendered board rather
 * than trusting to the stylesheet.
 */

import { expect, test } from "@playwright/test";
import { budget, startGame, takeAction, waitForOurTurn } from "./helpers";
import { frameWidths, MIN_FRAME, MIN_SCRIM, scrimFailures } from "./legibilityAssert";

async function buildABoard(page: import("@playwright/test").Page, steps = 14) {
  await waitForOurTurn(page);
  for (let i = 0; i < steps; i += 1) {
    if (
      await page
        .getByTestId("game-over")
        .isVisible()
        .catch(() => false)
    )
      return;
    await takeAction(page, ["keep", "play_land", "cast", "pass"]);
  }
}

test("every card's text is scrimmed against its own art", async ({ page }) => {
  test.setTimeout(budget(180_000));
  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
  await buildABoard(page);

  const bad = await page.evaluate(scrimFailures, MIN_SCRIM);

  expect(bad, "card text is sitting on an illustration with too little scrim").toEqual([]);
});

test("the frame is thick enough to read at pod sizes", async ({ page }) => {
  test.setTimeout(budget(180_000));
  await startGame(page, { deck: "aesi", opponents: 3, seed: 5 });
  await buildABoard(page, 20);

  const widths = await page.evaluate(frameWidths, ".mat--compact .face");

  if (widths.length === 0) test.skip(true, "no opponent permanents on the board yet");
  // The smallest card in a four-player pod is ~51px. At that size the border
  // still has to be a line rather than a suggestion.
  for (const width of widths) {
    expect(width).toBeGreaterThanOrEqual(MIN_FRAME);
  }
});
