/**
 * Does card type survive without colour?
 *
 * `tests/palette.test.ts` reads `cards.css` off disk, which is the right place
 * to guard the ladder but cannot see an override landing from `theme.css`, a
 * media query, or an inline style. These read the *resolved* values off real
 * elements in a real browser, which is the only way to know what actually
 * shipped.
 *
 * This is the check mockups/README.md says board art costs you. It is here
 * because the art was taken anyway, and a claim nobody can falsify is not worth
 * making.
 */

import { expect, test } from "@playwright/test";
import { startGame, takeAction, waitForOurTurn } from "./helpers";

/** The floor `palette.test.ts` uses; the same number, for the same reason. */
const MIN_GAP = 0.03;

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

test("every card type on the board is separable without colour", async ({ page }) => {
  test.setTimeout(180_000);
  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
  await buildABoard(page);

  const rings = await page.evaluate(() => {
    const channel = (v: number) => {
      const c = v / 255;
      return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    };
    const luminance = (colour: string) => {
      // Registered custom properties resolve to `rgb(...)`, but be tolerant of
      // a hex: parsing digits out of "#4f3c15" with a number regex yields
      // nonsense that still looks like a valid reading, which is the worst
      // kind of test bug.
      let rgb: number[] | null = null;
      const hex = colour.match(/^#([0-9a-f]{6})$/i);
      if (hex) {
        const n = Number.parseInt(hex[1], 16);
        rgb = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
      } else {
        const m = colour.match(/-?\d+(?:\.\d+)?/g);
        if (m && m.length >= 3) rgb = m.slice(0, 3).map(Number);
      }
      if (!rgb) return null;
      const [r, g, b] = rgb;
      return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
    };
    const byTone: Record<string, number> = {};
    for (const face of document.querySelectorAll<HTMLElement>(".face")) {
      const tone = face.dataset.typeTone;
      if (!tone) continue;
      const value = getComputedStyle(face).getPropertyValue("--type-ring").trim();
      const lum = luminance(value);
      if (lum !== null) byTone[tone] = lum;
    }
    return byTone;
  });

  const tones = Object.entries(rings).sort((a, b) => a[1] - b[1]);
  expect(tones.length, "no card faces carried a resolved --type-ring").toBeGreaterThan(1);

  for (let i = 1; i < tones.length; i += 1) {
    const [lower, low] = tones[i - 1];
    const [upper, high] = tones[i];
    expect(
      high - low,
      `${lower} and ${upper} are on screen together and indistinguishable in greyscale`,
    ).toBeGreaterThan(MIN_GAP);
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
