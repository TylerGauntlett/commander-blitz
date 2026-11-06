/**
 * The scale a short handheld lays out at (ADR 0028).
 *
 * The rule: a handheld-band screen shorter than the Deck is laid out at the
 * Deck's height and scaled to fit; every other size keeps the natural tag.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { layoutModeForSize, PHONE_MAX_H } from "../src/logic/breakpoints";
import {
  HANDHELD_DESIGN_H,
  layoutWidth,
  NATURAL_VIEWPORT,
  viewportContent,
  viewportScale,
} from "../src/logic/viewportScale";
import { DECK, PHONE_VIEWPORTS } from "../src/testing/devices";

describe("viewportScale", () => {
  it("leaves the Deck, a desktop and every phone alone", () => {
    expect(viewportScale(DECK.width, DECK.height)).toBe(1);
    expect(viewportScale(1600, 950)).toBe(1);
    for (const viewport of PHONE_VIEWPORTS) {
      expect(viewportScale(viewport.size.width, viewport.size.height)).toBe(1);
    }
  });

  it("leaves a handheld at least as tall as the Deck alone", () => {
    expect(viewportScale(820, 1180)).toBe(1);
    expect(viewportScale(1200, HANDHELD_DESIGN_H)).toBe(1);
  });

  it("brings a shorter handheld up to the design height, and still a handheld", () => {
    for (const [w, h] of [
      [1000, 703],
      [910, 703],
      [1000, 600],
      [1366, 520],
      [640, PHONE_MAX_H + 1],
    ]) {
      const scale = viewportScale(w, h);
      expect(scale).toBeLessThan(1);
      expect(scale).toBeGreaterThanOrEqual(PHONE_MAX_H / HANDHELD_DESIGN_H);
      const layoutW = layoutWidth(w, h);
      const layoutH = (layoutW * h) / w;
      expect(layoutH).toBeGreaterThanOrEqual(HANDHELD_DESIGN_H);
      expect(layoutH).toBeLessThan(HANDHELD_DESIGN_H + 2);
      expect(layoutModeForSize(layoutW, Math.floor(layoutH))).toBe("handheld");
    }
  });

  it("writes the natural tag when it does not scale, and an explicit width when it does", () => {
    expect(viewportContent(DECK.width, DECK.height)).toBe(NATURAL_VIEWPORT);
    expect(viewportContent(1000, 703)).toBe(
      "width=1138, initial-scale=0.8788, viewport-fit=cover",
    );
  });
});

it("is the tag index.html ships, so the first paint and the reset agree", () => {
  const html = readFileSync(join(__dirname, "..", "index.html"), "utf8");
  expect(html).toContain(`<meta name="viewport" content="${NATURAL_VIEWPORT}" />`);
});
