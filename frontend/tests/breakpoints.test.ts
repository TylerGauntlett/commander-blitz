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
  isCompact,
  isHandheldSize,
  isPhoneSize,
  layoutModeForSize,
  PHONE_MAX_H,
  PHONE_MAX_W,
  PHONE_QUERY,
} from "../src/logic/breakpoints";
import { PHONE_VIEWPORTS, VIEWPORTS } from "../src/testing/devices";

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

  it("is a size the handheld query also matches, which is why it is asked first", () => {
    for (const [w, h] of [
      [390, 844],
      [926, 428],
      [PHONE_MAX_W, 2000],
      [3000, PHONE_MAX_H],
    ]) {
      expect(isPhoneSize(w, h)).toBe(true);
      expect(isHandheldSize(w, h)).toBe(true);
      expect(layoutModeForSize(w, h)).toBe("phone");
    }
  });
});

describe("layoutModeForSize", () => {
  /*
   * ADR 0025: the three layouts are peers, so a size is exactly one of them.
   * Nesting the phone inside the handheld mode would hand every Deck rule to
   * every phone again, which is the failure the decision exists to prevent.
   */
  it("gives every size exactly one mode", () => {
    expect(layoutModeForSize(1600, 950)).toBe("desktop");
    expect(layoutModeForSize(1280, 800)).toBe("handheld");
    expect(layoutModeForSize(1200, 800)).toBe("handheld");
    expect(layoutModeForSize(393, 659)).toBe("phone");
    expect(layoutModeForSize(734, 343)).toBe("phone");
  });

  it("puts every viewport `testing/devices.ts` names in the layout it claims", () => {
    for (const viewport of VIEWPORTS) {
      expect(layoutModeForSize(viewport.size.width, viewport.size.height), viewport.id).toBe(
        viewport.layout,
      );
    }
    for (const viewport of PHONE_VIEWPORTS) expect(viewport.layout).toBe("phone");
  });

  it("calls only the two small modes compact", () => {
    expect(isCompact("desktop")).toBe(false);
    expect(isCompact("handheld")).toBe(true);
    expect(isCompact("phone")).toBe(true);
  });
});

describe("the layout attributes", () => {
  /*
   * The old names nested the modes: `data-phone` meant "and also a handheld".
   * They are gone, so no sheet can key a rule on them and reach two modes
   * without saying so.
   */
  it("are no longer the nested pair in any stylesheet", () => {
    for (const sheet of [css, phoneCss]) {
      expect(sheet).not.toMatch(/\[data-(handheld|phone|desktop)\]/);
    }
  });

  it("key phone.css's rules on the phone mode", () => {
    expect(phoneCss).toContain('[data-layout="phone"]');
  });
});
