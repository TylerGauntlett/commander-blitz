/**
 * Is the board readable without colour?
 *
 * `tests/palette.test.ts` reads `cards.css` off disk, which is the right place
 * to guard a number but cannot see an override landing from `theme.css`, a media
 * query, or an inline style. These read the *resolved* values off real elements
 * in a real browser, which is the only way to know what actually shipped.
 *
 * This is the check mockups/README.md says board art costs you. It is here
 * because the art was taken anyway -- and taken to the edge, now that the card
 * is a full-bleed illustration -- and a claim nobody can falsify is not worth
 * making.
 *
 * The first test used to walk an eight-step `--type-ring` luminance ladder,
 * because card type was encoded as the colour of the card stock. That encoding
 * was removed with the art-bleed redesign (docs/mockup-fidelity.md), so what is
 * checked here now is the thing the ladder was a proxy for: text on a card has
 * to be readable over an illustration nobody chose.
 */

import { expect, test } from "@playwright/test";
import { startGame, takeAction, waitForOurTurn } from "./helpers";

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
  test.setTimeout(180_000);
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

test("the type line survives greyscale on every face", async ({ page }) => {
  // Card type used to be the colour of the card stock. With that ladder gone,
  // this line and the glyph below are what is left, so they have to be *there*
  // -- laid out and non-empty -- rather than merely styled.
  test.setTimeout(180_000);
  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
  await buildABoard(page);

  await page.addStyleTag({ content: "html { filter: grayscale(1) !important; }" });

  const types = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>(".face")].map((face) => {
      const line = face.querySelector<HTMLElement>(".face__type");
      return {
        name: face.dataset.cardName ?? "?",
        text: (line?.textContent ?? "").trim(),
        visible: line ? line.getBoundingClientRect().width > 0 : false,
      };
    }),
  );

  expect(types.length).toBeGreaterThan(0);
  for (const line of types) {
    expect(line.text.length, `${line.name} has no type line`).toBeGreaterThan(0);
    expect(line.visible, `${line.name}'s type line is not rendered`).toBe(true);
  }
});

test("the type glyph stays visible in greyscale", async ({ page }) => {
  test.setTimeout(180_000);
  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
  await buildABoard(page);

  await page.addStyleTag({ content: "html { filter: grayscale(1) !important; }" });

  const glyphs = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>(".face")].map((face) => {
      const glyph = face.querySelector<HTMLElement>(".face__glyph");
      return {
        name: face.dataset.cardName ?? "?",
        text: glyph?.textContent ?? "",
        visible: glyph ? glyph.getBoundingClientRect().width > 0 : false,
      };
    }),
  );

  expect(glyphs.length).toBeGreaterThan(0);
  for (const glyph of glyphs) {
    // The non-colour cue of last resort. Whatever the art is doing, and
    // whatever a viewer's colour vision is doing, this still says what kind of
    // card it is.
    expect(glyph.text.length, `${glyph.name} has no type glyph`).toBe(1);
    expect(glyph.visible, `${glyph.name}'s type glyph is not rendered`).toBe(true);
  }
});

test("the commander's state survives without colour", async ({ page }) => {
  // The playable rim says "you can cast this" in green and in nothing else,
  // which is the top-ranked open defect in docs/mockup-fidelity.md. The plinth
  // that replaced the command-zone card is not allowed to add to that pile, so
  // it carries a word and a glyph as well as the frame colour.
  test.setTimeout(180_000);
  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
  await waitForOurTurn(page);
  await expect(page.getByTestId("command-zone-0")).toBeVisible();

  await page.addStyleTag({ content: "html { filter: grayscale(1) !important; }" });

  const plinths = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>(".cmdslot")].map((slot) => {
      const box = (node: Element | null) => (node?.getBoundingClientRect().width ?? 0) > 0;
      return {
        state: slot.dataset.cmdState ?? "",
        word: slot.querySelector(".cmdplinth__word")?.textContent ?? "",
        wordVisible: box(slot.querySelector(".cmdplinth__word")),
        glyph: slot.querySelector(".cmdplinth__glyph")?.textContent ?? "",
        glyphVisible: box(slot.querySelector(".cmdplinth__glyph")),
      };
    }),
  );

  expect(plinths.length, "no commander plinth on screen").toBeGreaterThan(0);
  for (const plinth of plinths) {
    expect(plinth.state, "a plinth rendered with no state at all").not.toBe("");
    // Two non-colour channels, both actually laid out rather than merely in the
    // DOM: a `display: none` label is not a channel.
    expect(plinth.word.length, `${plinth.state} says nothing in words`).toBeGreaterThan(0);
    expect(plinth.wordVisible, `${plinth.state}'s word is not rendered`).toBe(true);
    expect(plinth.glyph.length, `${plinth.state} has no glyph`).toBeGreaterThan(0);
    expect(plinth.glyphVisible, `${plinth.state}'s glyph is not rendered`).toBe(true);
  }
});

test("the frame is thick enough to read at pod sizes", async ({ page }) => {
  test.setTimeout(180_000);
  await startGame(page, { deck: "aesi", opponents: 3, seed: 5 });
  await buildABoard(page, 20);

  const widths = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>(".mat--compact .face")].map((face) =>
      Number.parseFloat(getComputedStyle(face).borderTopWidth),
    ),
  );

  if (widths.length === 0) test.skip(true, "no opponent permanents on the board yet");
  // Colour identity lives on this border; at the smallest card on screen it
  // still has to be a line rather than a suggestion.
  for (const width of widths) {
    expect(width).toBeGreaterThanOrEqual(1.5);
  }
});
