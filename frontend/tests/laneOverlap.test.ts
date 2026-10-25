/**
 * A handheld lane overlaps its cards instead of wrapping them.
 *
 * The playtest report: four artifacts on a Steam Deck put the global lane -- a
 * third of the front band, two cards wide -- onto a second row, the front band
 * grew a card taller, and the lands and the viewer's own seat went off the
 * bottom of the screen. `handheld.css` now fans a full lane; this holds the
 * solver to the same picture, and the stylesheet to the solver's number.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  bandsFor,
  boardHeight,
  type GroupFootprint,
  LANE_CHROME,
  type LaneFit,
  OVERLAP_MIN_VISIBLE,
  solveBoardCardWidth,
  wrapRows,
} from "../src/logic/zoomFit";

const HANDHELD_CSS = readFileSync(
  resolve(process.cwd(), "src/styles/handheld.css"),
  "utf-8",
).replace(/\r\n/g, "\n");

const plain = (n: number): GroupFootprint[] =>
  Array.from({ length: n }, () => ({ tapped: false, plies: 0, attachments: 0 }));

const lane = (n: number, widthPx: number, overlap: boolean): LaneFit => ({
  groups: plain(n),
  widthPx,
  labelAbove: false,
  overlap,
});

/** The screenshot's global lane: about a third of a Deck's board, 120px cards. */
const GLOBAL_W = 280;
const CARD_W = 120;

describe("an overlapping lane is one row", () => {
  it("four cards in a two-card lane wrap without overlap", () => {
    expect(wrapRows(lane(4, GLOBAL_W, false), CARD_W)).toBe(2);
  });

  it("and stay on one row with it", () => {
    expect(wrapRows(lane(4, GLOBAL_W, true), CARD_W)).toBe(1);
  });

  it("until even the tightest fan cannot fit, when the solver is told it overflows", () => {
    // Each squeezed slot is 0.22 * 120 + 12 = 38.4px; the last is a whole card.
    const fits = Math.floor(
      (GLOBAL_W - CARD_W) / (CARD_W * OVERLAP_MIN_VISIBLE + LANE_CHROME.gapX),
    );
    expect(wrapRows(lane(fits + 1, GLOBAL_W, true), CARD_W)).toBe(1);
    expect(wrapRows(lane(fits + 2, GLOBAL_W, true), CARD_W)).toBeGreaterThan(1);
  });
});

describe("the board stops growing", () => {
  const footprints = (artifacts: number) => ({
    Creatures: plain(3),
    "Artifacts & Enchantments": plain(artifacts),
    Lands: plain(1),
  });

  it("a fourth artifact adds no height to a handheld board", () => {
    const at = (n: number) =>
      boardHeight(bandsFor(footprints(n), 840, { labels: false, overlap: true }), CARD_W);
    expect(at(4)).toBe(at(2));
  });

  it("and the solver keeps the cards the size it had", () => {
    const budget = { heightPx: 420, minCardW: 96, maxCardW: 150 };
    const solve = (n: number) =>
      solveBoardCardWidth(
        bandsFor(footprints(n), 840, { labels: false, overlap: true }),
        budget,
      );
    expect(solve(4)).toBe(solve(2));
  });

  it("the desktop board, which does not overlap, still wraps", () => {
    const at = (n: number) => boardHeight(bandsFor(footprints(n), 840, {}), CARD_W);
    expect(at(4)).toBeGreaterThan(at(2));
  });
});

describe("handheld.css draws what the solver assumes", () => {
  it("never wraps the viewer's lanes", () => {
    expect(HANDHELD_CSS).toMatch(
      /\[data-compact\] \.play__mine \.lane__cards \{\s*flex-wrap: nowrap;/,
    );
  });

  it("keeps OVERLAP_MIN_VISIBLE of every card showing", () => {
    const match = HANDHELD_CSS.match(
      /\.play__mine \.lane__cards > \.cardstack \{[^}]*min-width: calc\(var\(--card-w\) \* ([\d.]+)\)/,
    );
    expect(Number(match?.[1])).toBe(OVERLAP_MIN_VISIBLE);
  });

  it("pins the viewer's seat column", () => {
    expect(HANDHELD_CSS).toMatch(
      /\[data-compact\] \.play__mine \.mat__side \{\s*position: sticky;/,
    );
  });
});
