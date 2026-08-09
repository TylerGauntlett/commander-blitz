/**
 * Card geometry.
 *
 * These ratios replaced nine hard-coded pixel constants. The one thing worth
 * asserting is that they still reproduce the sizes the board was designed and
 * playtested at -- a ratio typo is invisible in code review and shows up as a
 * lane that silently wraps.
 */

import { describe, expect, it } from "vitest";
import {
  CARD_SCALE,
  FALLBACK_BASE,
  MAX_CARD_W,
  MIN_CARD_W,
  cardWidthPx,
  cardWidthVar,
  opponentCardScale,
} from "../src/logic/cardSize";

/** The pixel widths every ratio was derived from, at the old fixed base. */
const ORIGINAL_PX = {
  own: 104,
  hand: 146,
  preview: 236,
  peek: 150,
  stack: 116,
  spotlight: 190,
  commandSlot: 108,
} as const;

describe("zone ratios", () => {
  it.each(Object.keys(ORIGINAL_PX) as (keyof typeof ORIGINAL_PX)[])(
    "reproduces the original %s width at the old base",
    (zone) => {
      const px = cardWidthPx(FALLBACK_BASE, CARD_SCALE[zone]);
      // Within a pixel: the ratios are rounded to 2-3 places on purpose, so
      // the emitted calc() stays readable.
      expect(Math.abs(px - ORIGINAL_PX[zone])).toBeLessThanOrEqual(1);
    },
  );

  it("keeps the hand larger than the board", () => {
    // The hand is the only zone where rules text has to be readable, which is
    // the whole reason it is bigger than a battlefield card.
    expect(CARD_SCALE.hand).toBeGreaterThan(CARD_SCALE.own);
  });

  it("makes the preview the largest card on screen", () => {
    const largest = Math.max(...Object.values(CARD_SCALE));
    expect(CARD_SCALE.preview).toBe(largest);
  });
});

describe("opponentCardScale", () => {
  it.each([
    [1, 82],
    [2, 72],
    [3, 60],
    [4, 60],
  ])("gives %i opponent(s) the original %ipx", (count, px) => {
    expect(Math.abs(cardWidthPx(FALLBACK_BASE, opponentCardScale(count)) - px)).toBeLessThan(1);
  });

  it("never grows as opponents are added", () => {
    // Three mats at full size wrap their lands and start scrolling, which puts
    // a permanent one scroll away in the zone you most need to survey.
    const scales = [1, 2, 3, 4, 8].map(opponentCardScale);
    for (let i = 1; i < scales.length; i += 1) {
      expect(scales[i]).toBeLessThanOrEqual(scales[i - 1]);
    }
  });

  it("keeps every opponent smaller than the viewer", () => {
    expect(opponentCardScale(1)).toBeLessThan(CARD_SCALE.own);
  });
});

describe("cardWidthVar", () => {
  it("emits a calc against the fluid base, never a pixel literal", () => {
    // This is the bug the whole refactor exists to fix: an inline `104px`
    // overrides any clamp() on :root, so a 2560px display showed exactly the
    // same small cards a 1366px one did.
    const value = cardWidthVar(CARD_SCALE.own);
    expect(value).toContain("var(--card-w-base)");
    expect(value).not.toMatch(/\d+px/);
  });

  it("rounds away float noise", () => {
    expect(cardWidthVar(1 / 3)).toBe("calc(var(--card-w-base) * 0.333)");
  });

  /**
   * The rule that keeps progressive zoom honest.
   *
   * A zone hands the same coefficient to CSS (as a `calc()`) and to JavaScript (as
   * a number), because the hand fan positions its slots absolutely and `CardStack`
   * measures its own container. If those two ever disagreed about the zoom the
   * cards would render at one size and be laid out at another -- so assert that
   * the number and the emitted coefficient are the same thing.
   */
  it("agrees with cardWidthPx about what a scale means", () => {
    for (const scale of [0.5, 0.58, 1, 1.4, 1.732, 2.27]) {
      const emitted = cardWidthVar(scale);
      const coefficient = Number.parseFloat(
        (emitted.match(/\*\s*([\d.]+)\s*\)/) as RegExpMatchArray)[1],
      );
      expect(cardWidthPx(FALLBACK_BASE, scale)).toBeCloseTo(FALLBACK_BASE * coefficient, 0);
    }
  });
});

describe("the legibility bounds the zoom works inside", () => {
  it("never shrinks below the smallest size the suite has checked", () => {
    // e2e/legibility.spec.ts measures the frame off a three-opponent pod, whose
    // cards are this wide at a 950px-tall viewport.
    const smallestChecked = cardWidthPx(87.4, opponentCardScale(3));
    expect(MIN_CARD_W).toBeGreaterThanOrEqual(smallestChecked);
    expect(MIN_CARD_W).toBeLessThan(smallestChecked + 2);
  });

  it("never grows past the preview rail's own card", () => {
    // `.face--big` pins the preview to 150px. A board card wider than that would
    // set its type larger than the panel whose job is to be the readable copy.
    expect(MAX_CARD_W).toBe(150);
  });

  it("leaves today's playtested sizes inside the band", () => {
    for (const scale of [opponentCardScale(3), CARD_SCALE.own, CARD_SCALE.hand]) {
      const px = cardWidthPx(87.4, scale);
      expect(px).toBeGreaterThanOrEqual(MIN_CARD_W - 2);
      expect(px).toBeLessThanOrEqual(MAX_CARD_W);
    }
  });
});
