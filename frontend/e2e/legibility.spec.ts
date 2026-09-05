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

/**
 * How dark a scrim has to be at the end the text sits on.
 *
 * The same floor `tests/palette.test.ts` parses out of the stylesheet, checked
 * here against what the browser actually resolved. White type at 0.7 is
 * readable over the brightest crop in `data/art`; below that it depends on
 * which card you happen to be looking at, which is not a property.
 */
const MIN_SCRIM = 0.7;

test("every card's text is scrimmed against its own art", async ({ page }) => {
  test.setTimeout(budget(180_000));
  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
  await buildABoard(page);

  const bad = await page.evaluate((floor) => {
    /** The most opaque black stop in a resolved `linear-gradient(...)`. */
    const peak = (background: string) => {
      const stops = [...background.matchAll(/rgba?\(([^)]*)\)/g)].map((m) =>
        m[1].split(/[,/]/).map((n) => Number.parseFloat(n.trim())),
      );
      const alphas = stops
        // Only the dark stops count: a scrim is black fading to nothing, and
        // the transparent end is the look rather than the legibility.
        .filter((c) => c.length >= 3 && c[0] < 60 && c[1] < 60 && c[2] < 60)
        .map((c) => (c.length >= 4 ? c[3] : 1));
      return alphas.length > 0 ? Math.max(...alphas) : 0;
    };

    const failures: string[] = [];
    for (const face of document.querySelectorAll<HTMLElement>(".face")) {
      const name = face.dataset.cardName ?? "?";
      for (const part of ["face__head", "face__foot"]) {
        const band = face.querySelector<HTMLElement>(`.${part}`);
        if (!band) {
          failures.push(`${name}: no .${part}`);
          continue;
        }
        const alpha = peak(getComputedStyle(band).backgroundImage);
        if (alpha < floor) failures.push(`${name}: .${part} peaks at ${alpha}`);
      }
    }
    return failures;
  }, MIN_SCRIM);

  expect(bad, "card text is sitting on an illustration with too little scrim").toEqual([]);
});

test("the frame is thick enough to read at pod sizes", async ({ page }) => {
  test.setTimeout(budget(180_000));
  await startGame(page, { deck: "aesi", opponents: 3, seed: 5 });
  await buildABoard(page, 20);

  const widths = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>(".mat--compact .face")].map((face) =>
      Number.parseFloat(getComputedStyle(face).borderTopWidth),
    ),
  );

  if (widths.length === 0) test.skip(true, "no opponent permanents on the board yet");
  // The smallest card in a four-player pod is ~51px. At that size the border
  // still has to be a line rather than a suggestion.
  for (const width of widths) {
    expect(width).toBeGreaterThanOrEqual(1.5);
  }
});
