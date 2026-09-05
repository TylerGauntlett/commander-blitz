/**
 * The opening hand's arch, as arithmetic.
 *
 * Two claims, and neither is provable by looking at the screen.
 *
 * **Nothing moves when the selection does.** That is the whole third pass of
 * the mulligan round's 01 'The Deal' (`docs/design-record.md#mulligan`), and a screenshot cannot show it -- a
 * still of a row that slides is indistinguishable from a still of one that does
 * not. `handRow` not taking a selected index at all is the design; these tests
 * are what stop somebody adding one.
 *
 * **The row stays on the stage at every size.** The mockup's first draft put
 * both end cards 4px from the bezel, which its own overflow gate passed because
 * 4px is inside. The reach a rotation adds is `reachRatio`, and asserting it
 * across the whole clamp range is the falsifiable version of "it looked fine".
 */

import { describe, expect, it } from "vitest";
import { stageScale } from "../src/logic/doorRow";
import {
  MULLIGAN_BOTTOM,
  MULL_TUNE,
  handRow,
  mulliganPhase,
  rowExtent,
  rowRatio,
  stageUnit,
  zFor,
} from "../src/logic/openingHand";
import { gameView, pending, player } from "../src/testing/fixtures";

const HAND = 7;

/** The row as it is drawn on a Deck, which is the composition of record. */
const deck = () => handRow(HAND, 1280, stageUnit(1280, 800, HAND));

describe("the composition at 1280x800", () => {
  it("is the mockup's, to the pixel", () => {
    expect(stageUnit(1280, 800, HAND)).toBe(1);

    const row = deck();
    expect(row.cardW).toBe(296);
    expect(row.cardH).toBeCloseTo(414.4, 1);
    expect(row.pitch).toBe(144);
    // 6 x 144 + 296 = 1160, centred on 1280.
    expect(row.width).toBe(1160);
    expect(row.left).toBe(60);
    expect(row.top).toBe(100);
  });

  it("pins the arch to the middle of the row, not to a selection", () => {
    const row = deck();
    // The middle card is the upright one and sits highest; the ends lean away
    // from it by three steps and drop by nine sags.
    expect(row.slots[3].rot).toBe(0);
    expect(row.slots[3].y).toBe(0);
    expect(row.slots[0].rot).toBeCloseTo(-3 * MULL_TUNE.SPREAD, 10);
    expect(row.slots[6].rot).toBeCloseTo(3 * MULL_TUNE.SPREAD, 10);
    expect(row.slots[0].y).toBeCloseTo(9 * MULL_TUNE.SAG, 10);
    expect(row.slots[6].y).toBeCloseTo(9 * MULL_TUNE.SAG, 10);
  });

  it("is symmetric about its own centre", () => {
    const row = deck();
    for (let i = 0; i < HAND; i += 1) {
      const mirror = row.slots[HAND - 1 - i];
      expect(row.slots[i].y).toBeCloseTo(mirror.y, 10);
      expect(row.slots[i].rot).toBeCloseTo(-mirror.rot, 10);
    }
  });

  it("costs 33px per side for the tilt, which is what the 60px margin is for", () => {
    const row = deck();
    const { left, right } = rowExtent(row, HAND);
    // The boxes start at 60; the ink starts at 27, and the difference is the
    // rotation swinging the top outer corner out.
    expect(Math.round(left)).toBe(27);
    expect(Math.round(1280 - right)).toBe(27);
    expect(Math.round(row.left - left)).toBe(33);
  });
});

describe("nothing about the row depends on the selection", () => {
  it("has no way to be told what is selected", () => {
    // Three arguments: how many cards, how wide the stage, what scale. A fourth
    // is the defect this file exists to prevent.
    expect(handRow.length).toBe(3);
  });

  it("returns the identical geometry however many times it is asked", () => {
    expect(handRow(HAND, 1280, 1)).toEqual(handRow(HAND, 1280, 1));
  });
});

describe("the stack falls away from the card you are on", () => {
  it("puts the selected card on top, in both directions", () => {
    expect(zFor(3, 3)).toBe(100);
    expect(zFor(2, 3)).toBe(zFor(4, 3));
    expect(zFor(0, 3)).toBe(97);
    expect(zFor(6, 3)).toBe(97);
  });

  it("is monotone in distance, so no card ever jumps the one beside it", () => {
    for (let on = 0; on < HAND; on += 1) {
      for (let i = 1; i < HAND; i += 1) {
        const nearer = Math.abs(i - on) < Math.abs(i - 1 - on);
        if (nearer) expect(zFor(i, on)).toBeGreaterThan(zFor(i - 1, on));
      }
    }
  });
});

describe("the row stays on the stage", () => {
  /* Every size worth asking about: the Deck, the desktop suite's viewport, the
     second `deckfit` viewport, a tall narrow window where the WIDTH binds rather
     than the height, and the two ends of `stageScale`'s clamp. */
  const stages: [number, number][] = [
    [1280, 800],
    [1600, 950],
    [1200, 800],
    [1366, 820],
    [900, 1200],
    [800, 1200],
    [2560, 1440],
    [3840, 2160],
  ];

  for (const [w, h] of stages) {
    it(`fits ${w}x${h}`, () => {
      const unit = stageUnit(w, h, HAND);
      const row = handRow(HAND, w, unit);
      const { left, right } = rowExtent(row, HAND);
      expect(left).toBeGreaterThanOrEqual(0);
      expect(right).toBeLessThanOrEqual(w);
      // And the answers below the row still have somewhere to be.
      expect(row.top + row.height).toBeLessThan(MULL_TUNE.ACTS_TOP * unit);
    });
  }

  it("never draws type it would have to shrink, so the unit is the only thing that gives", () => {
    // The clamp's floor. Below this the composition would keep shrinking while
    // the 16px floor did not, which is the trade `stageScale` documents.
    expect(stageUnit(1280, 400, HAND)).toBeGreaterThanOrEqual(0.72);
    expect(stageUnit(4000, 4000, HAND)).toBeLessThanOrEqual(1.45);
  });

  it("takes the smaller of what the height wants and what the width can hold", () => {
    // A tall narrow window: `stageScale` alone would ask for 0.72 and run the
    // arch off both sides, because it only ever looks at height.
    expect(stageScale(800, 1200)).toBe(0.72);
    expect(stageUnit(800, 1200, HAND)).toBeLessThan(0.72);
    // A Deck is the other way round and the width term is never reached.
    expect(stageUnit(1280, 800, HAND)).toBe(stageScale(1280, 800));
  });

  it("needs 4.14 card widths for a hand of seven", () => {
    expect(rowRatio(HAND)).toBeCloseTo(4.14, 2);
    // Which is 1226px at a 296px card -- against a Deck's 1280.
    expect(rowRatio(HAND) * MULL_TUNE.CARD_W).toBeLessThan(1280);
  });
});

describe("which half of a mulligan it is", () => {
  const seatOne = () => [player({ pid: 0 }), player({ pid: 1, name: "AI 1" })];

  it("claims the keep-or-mulligan question", () => {
    const state = gameView({
      players: seatOne(),
      pending: pending({ kind: "mulligan", player: 0 }),
    });
    expect(mulliganPhase(state)).toBe("keep");
  });

  it("claims the bottoming question by its purpose, never by its prompt", () => {
    const state = gameView({
      players: seatOne(),
      pending: pending({
        kind: "choose_objects",
        player: 0,
        prompt: "Put 1 card(s) on the bottom of your library",
        context: { purpose: MULLIGAN_BOTTOM, source_name: "Mulligan" },
      }),
    });
    expect(mulliganPhase(state)).toBe("bottom");
  });

  it("leaves every other choose_objects to the dialog", () => {
    const state = gameView({
      players: seatOne(),
      pending: pending({
        kind: "choose_objects",
        player: 0,
        prompt: "Choose a creature to sacrifice",
        context: { purpose: "sacrifice" },
      }),
    });
    expect(mulliganPhase(state)).toBeNull();
  });

  it("says nothing when the question is somebody else's, or the game is over", () => {
    const mine = { players: seatOne(), pending: pending({ kind: "mulligan", player: 0 }) };
    expect(mulliganPhase(gameView(mine))).toBe("keep");
    expect(
      mulliganPhase(gameView({ ...mine, pending: pending({ kind: "mulligan", player: 1 }) })),
    ).toBeNull();
    expect(mulliganPhase(gameView({ ...mine, game_over: true }))).toBeNull();
    expect(mulliganPhase(gameView({ ...mine, pending: null }))).toBeNull();
  });
});
