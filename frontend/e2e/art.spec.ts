/**
 * Card art, in a real browser.
 *
 * The unit tests assert the markup; only this can assert that a byte actually
 * arrived and decoded. The property that matters most is the last one: the
 * board must talk to this server and nothing else, so a game keeps rendering
 * when Scryfall is rate limiting, down, or blocked.
 */

import { expect, test } from "@playwright/test";
import { startGame, takeAction, waitForOurTurn } from "./helpers";

/** Play far enough that permanents are on the board to look at. */
async function buildABoard(page: import("@playwright/test").Page, steps = 12) {
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

test("art loads and decodes on the board", async ({ page }) => {
  test.setTimeout(180_000);
  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
  await buildABoard(page);

  const decoded = await expect
    .poll(
      async () =>
        page.evaluate(() => {
          const images = [...document.querySelectorAll<HTMLImageElement>(".face__art img")];
          return images.filter((img) => img.naturalWidth > 0).length;
        }),
      { timeout: 20_000 },
    )
    .toBeGreaterThan(0)
    .then(() => true);
  expect(decoded).toBe(true);
});

test("every art request goes to this server, never to a third party", async ({ page }) => {
  test.setTimeout(180_000);
  const external: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (!url.startsWith("http://127.0.0.1") && !url.startsWith("http://localhost")) {
      external.push(url);
    }
  });

  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
  await buildABoard(page);

  // The whole point of downloading the crops at build time. If this fails the
  // board has a live dependency on somebody else's CDN again.
  expect(external, `the page fetched from outside: ${external.join(", ")}`).toEqual([]);
});

test("a card with no printing shows a plate, not a broken image", async ({ page }) => {
  test.setTimeout(180_000);
  // Forced rather than hunted for: whether an artless card reaches the board
  // depends on the shuffle, and a test that depends on the shuffle is a test
  // that fails on Tuesdays.
  await page.route("**/api/images", (route) =>
    route.fulfill({ json: { art_base: "/art", images: {} } }),
  );

  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
  await buildABoard(page);

  const state = await page.evaluate(() => {
    const faces = [...document.querySelectorAll(".face")];
    return {
      faces: faces.length,
      plates: faces.filter((f) => f.querySelector(".face__art--none")).length,
      images: document.querySelectorAll(".face__art img").length,
      // The plate is a fallback, not a blank: the card must still identify
      // itself by name and type glyph.
      named: faces.filter((f) => (f.querySelector(".face__name")?.textContent ?? "").length > 0)
        .length,
      glyphed: faces.filter(
        (f) => (f.querySelector(".face__glyph")?.textContent ?? "").length > 0,
      ).length,
    };
  });

  expect(state.faces).toBeGreaterThan(0);
  expect(state.plates).toBe(state.faces);
  expect(state.images).toBe(0);
  expect(state.named).toBe(state.faces);
  expect(state.glyphed).toBe(state.faces);
});

test("the art never covers the type ring", async ({ page }) => {
  test.setTimeout(180_000);
  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
  await buildABoard(page);

  const violations = await page.evaluate(() => {
    const bad: string[] = [];
    for (const face of document.querySelectorAll<HTMLElement>(".face")) {
      const art = face.querySelector<HTMLElement>(".face__art");
      if (!art) continue;
      const ring = Number.parseFloat(getComputedStyle(face).getPropertyValue("--type-ring-w"));
      if (!Number.isFinite(ring) || ring <= 0) {
        bad.push(`${face.dataset.cardName}: no ring width`);
        continue;
      }
      const f = face.getBoundingClientRect();
      const a = art.getBoundingClientRect();
      // The art must sit inside the frame by at least the ring, on all four
      // sides -- that inset is what keeps the type encoding visible.
      const insets = [a.left - f.left, f.right - a.right, a.top - f.top, f.bottom - a.bottom];
      if (insets.some((inset) => inset < ring)) {
        bad.push(`${face.dataset.cardName}: insets ${insets.map((n) => n.toFixed(1))}`);
      }
    }
    return bad;
  });

  expect(violations, "the art band is bleeding over the type ring").toEqual([]);
});

test("the preview rail credits the illustrator", async ({ page }) => {
  test.setTimeout(180_000);
  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
  await buildABoard(page);

  const card = page.locator(".play__mine .card").first();
  if ((await card.count()) === 0) test.skip(true, "no permanent on the board to hover");
  await card.hover();

  const preview = page.getByTestId("card-preview");
  await expect(preview).toBeVisible();
  // `Art` only appears when the map resolved an artist for this card.
  await expect.poll(async () => (await preview.textContent()) ?? "").toContain("Art");
});
