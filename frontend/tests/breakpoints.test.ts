/**
 * The handheld breakpoint.
 *
 * The query is stated twice -- once in `logic/breakpoints.ts` for `matchMedia`,
 * once in `styles/handheld.css` for the cascade -- because CSS cannot move a
 * component into a different parent and React cannot restyle a card as cheaply
 * as a stylesheet can. Two statements of one fact is a drift risk, and this is
 * the test that makes it safe: the stylesheet must contain the query verbatim.
 *
 * A drift here is otherwise invisible and vicious. CSS would compact the rails
 * while React kept rendering the left one, or React would move the log into an
 * overlay the stylesheet never gives a position to.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  HANDHELD_MAX_H,
  HANDHELD_MAX_W,
  HANDHELD_QUERY,
  PHONE_MAX_H,
  PHONE_MAX_W,
  PHONE_QUERY,
  isHandheldSize,
  isPhoneSize,
} from "../src/logic/breakpoints";

// `__dirname` rather than `import.meta.url`: under the jsdom project Vite
// rewrites the module URL to an http one and `fileURLToPath` refuses it.
// `tests/imports.test.ts` reads the tree the same way.
const css = readFileSync(join(__dirname, "..", "src", "styles", "handheld.css"), "utf8");

describe("HANDHELD_QUERY", () => {
  it("appears verbatim in handheld.css, so the two definitions cannot drift", () => {
    expect(css).toContain(`@media ${HANDHELD_QUERY}`);
  });

  it("is the only breakpoint handheld.css keys its layout on", () => {
    /*
     * A second, hand-written width query in the same file would be a third
     * definition of the same idea, and is exactly what this suite is for.
     * Feature and preference queries are a different question and are allowed.
     */
    const layoutQueries = [...css.matchAll(/@media\s+([^{]+)\{/g)]
      .map((match) => match[1].trim())
      .filter((query) => /max-width|min-width|max-height|min-height/.test(query));
    expect(layoutQueries.length).toBeGreaterThan(0);
    for (const query of layoutQueries) {
      expect(query).toBe(HANDHELD_QUERY);
    }
  });
});

describe("isHandheldSize", () => {
  it("claims a Steam Deck", () => {
    expect(isHandheldSize(1280, 800)).toBe(true);
  });

  it("claims a short-but-wide window, which is as hostile as a narrow one", () => {
    expect(isHandheldSize(1920, 720)).toBe(true);
  });

  it("leaves the viewports the suites are written at alone", () => {
    // If either of the first two ever returns true, every existing story and
    // every existing spec is suddenly reviewing a different layout.
    expect(isHandheldSize(1600, 950)).toBe(false);
    expect(isHandheldSize(2560, 1278)).toBe(false);
    expect(isHandheldSize(1920, 1080)).toBe(false);
  });

  it("is inclusive at both edges", () => {
    expect(isHandheldSize(HANDHELD_MAX_W, 1080)).toBe(true);
    expect(isHandheldSize(HANDHELD_MAX_W + 1, 1080)).toBe(false);
    expect(isHandheldSize(1920, HANDHELD_MAX_H)).toBe(true);
    expect(isHandheldSize(1920, HANDHELD_MAX_H + 1)).toBe(false);
  });
});

const phoneCss = readFileSync(join(__dirname, "..", "src", "styles", "phone.css"), "utf8");

describe("PHONE_QUERY", () => {
  it("appears verbatim in phone.css, so the two definitions cannot drift", () => {
    expect(phoneCss).toContain(`@media ${PHONE_QUERY}`);
  });

  it("is the only size breakpoint phone.css keys on", () => {
    // Orientation is a different question and is allowed; a second width or
    // height query would be a third definition of "phone".
    const sizeQueries = [...phoneCss.matchAll(/@media\s+([^{]+)\{/g)]
      .map((match) => match[1].trim())
      .filter((query) => /max-width|min-width|max-height|min-height/.test(query));
    expect(sizeQueries).toEqual([PHONE_QUERY]);
  });
});

describe("isPhoneSize", () => {
  it("claims a phone held either way", () => {
    expect(isPhoneSize(390, 844)).toBe(true);
    expect(isPhoneSize(428, 926)).toBe(true);
    expect(isPhoneSize(844, 390)).toBe(true);
    expect(isPhoneSize(926, 428)).toBe(true);
  });

  it("leaves the Deck and every desktop alone", () => {
    expect(isPhoneSize(1280, 800)).toBe(false);
    expect(isPhoneSize(1200, 800)).toBe(false);
    expect(isPhoneSize(1600, 950)).toBe(false);
  });

  it("is always a handheld too, because the tier is additive", () => {
    for (const [w, h] of [
      [390, 844],
      [926, 428],
      [PHONE_MAX_W, 2000],
      [3000, PHONE_MAX_H],
    ]) {
      expect(isPhoneSize(w, h)).toBe(true);
      expect(isHandheldSize(w, h)).toBe(true);
    }
  });
});
