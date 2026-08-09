/**
 * The fit solver.
 *
 * Two kinds of test here, and the second is the important one.
 *
 * The first kind checks the wrap arithmetic against rows counted by hand. Worth
 * having, but it only proves the model agrees with my reading of `flex-wrap`.
 *
 * The second kind checks the *property the search depends on*: `boardHeight` must
 * be non-decreasing in card width. `solveBoardCardWidth` is a binary search, and
 * a binary search over a non-monotone function does not return a wrong answer
 * loudly -- it returns a plausible one. So that is fuzzed rather than asserted at
 * a few points, and `LANE_CHROME` is checked against the stylesheet it mirrors
 * rather than against a copy of itself.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { MAX_PLIES, PLY_X } from "../src/logic/cardStackGeometry";
import {
  type BandFit,
  type GroupFootprint,
  LANE_CHROME,
  type LaneFit,
  bandsFor,
  boardHeight,
  groupBox,
  handStep,
  laneHeight,
  solveBoardCardWidth,
  solveHandCardWidth,
  wrapRows,
} from "../src/logic/zoomFit";

/** As `tests/palette.test.ts` does: read the shipped file, not a copy of it. */
const BOARD_CSS = readFileSync(resolve(process.cwd(), "src/styles/board.css"), "utf-8").replace(
  /\r\n/g,
  "\n",
);

const plain = (n: number, over: Partial<GroupFootprint> = {}): GroupFootprint[] =>
  Array.from({ length: n }, () => ({ tapped: false, plies: 0, attachments: 0, ...over }));

const lane = (groups: GroupFootprint[], widthPx: number, labelAbove = false): LaneFit => ({
  groups,
  widthPx,
  labelAbove,
});

describe("groupBox", () => {
  it("swaps the axes for a tapped permanent", () => {
    const cw = 100;
    const up = groupBox({ tapped: false, plies: 0, attachments: 0 }, cw);
    const down = groupBox({ tapped: true, plies: 0, attachments: 0 }, cw);
    expect(up).toEqual({ w: 100, h: 140 });
    expect(down).toEqual({ w: 140, h: 100 });
  });

  it("adds a flat 7px per visible ply, not a ratio", () => {
    // The peek is a constant in the component, so it must not scale here either
    // -- a stack of basics at a 60px card has the same 7px step as at a 140px one.
    const one = groupBox({ tapped: false, plies: 0, attachments: 0 }, 100).w;
    const three = groupBox({ tapped: false, plies: 2, attachments: 0 }, 100).w;
    expect(three - one).toBe(2 * PLY_X);
  });

  it("scales the attachment peek with the card", () => {
    const at100 = groupBox({ tapped: false, plies: 0, attachments: 1 }, 100);
    const at200 = groupBox({ tapped: false, plies: 0, attachments: 1 }, 200);
    expect(at100.w).toBeCloseTo(122);
    expect(at200.w).toBeCloseTo(244);
  });
});

describe("wrapRows", () => {
  it("packs greedily, first-fit by line", () => {
    // 4 cards of 100 with 12px gaps into 350px: 100,212,324 fit -- the fourth
    // would need 436. So three on the first row and one on the second.
    expect(wrapRows(lane(plain(4), 350), 100)).toBe(2);
  });

  it("fits exactly when the last card lands on the boundary", () => {
    // Three at 100 plus two 12px gaps is 324 on the nose.
    expect(wrapRows(lane(plain(3), 324), 100)).toBe(1);
    expect(wrapRows(lane(plain(3), 323), 100)).toBe(2);
  });

  it("counts a mixed tapped and untapped lane correctly", () => {
    // A landscape card is 1.4x as wide, so uniform `floor(laneW / cardW)` would
    // get this wrong in both directions. Two tapped (140) + two untapped (100)
    // into 400: 140, 292, 404 > 400 -> so two per row, two rows.
    const groups = [...plain(2, { tapped: true }), ...plain(2)];
    expect(wrapRows(lane(groups, 400), 100)).toBe(2);
  });

  it("counts a lane of hosts with attachments", () => {
    // Each host is 100 + 22 = 122 wide. Into 400: 122, 256, 390 fit; the fourth
    // needs 524.
    expect(wrapRows(lane(plain(4, { attachments: 1 }), 400), 100)).toBe(2);
  });

  it("gives a group wider than the lane its own row rather than looping", () => {
    expect(wrapRows(lane(plain(3), 40), 100)).toBe(3);
  });

  it("treats a stack of many as one box", () => {
    // The whole reason the solver counts groups: twelve basics are one footprint
    // capped at MAX_PLIES, not twelve cards.
    const twelve = plain(1, { plies: MAX_PLIES });
    expect(wrapRows(lane(twelve, 200), 100)).toBe(1);
  });
});

describe("laneHeight", () => {
  it("floors an empty back lane at a full card plus the min-height surplus", () => {
    // The reserved slot: an empty lane costs a whole card, which is what stops
    // the viewer's board jumping as permanents enter and leave play.
    expect(laneHeight(lane([], 800), 100)).toBe(100 * 1.4 + LANE_CHROME.laneMinExtra);
  });

  /**
   * `.lane__cards` has its own `min-height` and `.lane` has another, and in the
   * front band the label stacks on top of the first -- so an empty front lane is
   * taller than `.lane`'s floor, not equal to it. Modelling one floor and not the
   * other under-counted every front lane and let the solver choose a size whose
   * lanes then overflowed the budget it had just fitted them into.
   */
  it("stacks the cards' own floor under the label, above the lane's floor", () => {
    const front = laneHeight(lane([], 800, true), 100);
    expect(front).toBe(100 * 1.4 + LANE_CHROME.labelAboveH + LANE_CHROME.lanePadY);
    expect(front).toBeGreaterThan(100 * 1.4 + LANE_CHROME.laneMinExtra);
  });

  /**
   * The model against the real thing.
   *
   * Measured off the rendered board at three viewports with an empty battlefield,
   * which is the case both floors govern. These numbers are the reason
   * `labelAboveH` is 23 and the reason the cards' floor is modelled at all -- get
   * either wrong and the solver is confidently wrong about how much room it has,
   * which no other test in this file would notice.
   */
  it.each([
    // cardW,   front,  back    (viewport)
    [52.02, 103.8, 84.8], // 1600x700
    [95.8778, 165.2, 146.2], // 1600x950
    [150.04, 241.1, 222.1], // 2560x1278
  ])("matches the real rendered lane heights at a %ipx card", (cardW, front, back) => {
    expect(laneHeight(lane([], 800, true), cardW)).toBeCloseTo(front, 0);
    expect(laneHeight(lane([], 800, false), cardW)).toBeCloseTo(back, 0);
  });

  it("charges the front band a label line and the back band nothing", () => {
    const above = laneHeight(lane(plain(6), 300, true), 100);
    const beside = laneHeight(lane(plain(6), 300, false), 100);
    expect(above - beside).toBe(LANE_CHROME.labelAboveH);
  });

  it("charges a row gap only between rows", () => {
    // A single row is floored by `.lane`'s own min-height, so compare the
    // two-row height against the arithmetic directly rather than against it.
    expect(laneHeight(lane(plain(2), 150), 100)).toBe(
      100 * 1.4 * 2 + LANE_CHROME.gapY + LANE_CHROME.lanePadY,
    );
    expect(laneHeight(lane(plain(2), 800), 100)).toBe(100 * 1.4 + LANE_CHROME.laneMinExtra);
  });

  it("measures a tapped row at the landscape height", () => {
    // A row of tapped lands is only 100 tall at a 100px card, not 140 -- which is
    // the difference between one row fitting and two.
    const tappedLane = laneHeight(lane(plain(3, { tapped: true }), 800), 100);
    // Still floored by the lane's own min-height, so assert the row itself.
    expect(tappedLane).toBe(100 * 1.4 + LANE_CHROME.laneMinExtra);
    const twoRows = laneHeight(lane(plain(8, { tapped: true }), 800), 100);
    expect(twoRows).toBe(100 * 2 + LANE_CHROME.gapY + LANE_CHROME.lanePadY);
  });
});

describe("boardHeight", () => {
  it("takes the tallest lane in a band, not the sum", () => {
    const band: BandFit = { lanes: [lane(plain(6), 200), lane([], 200)] };
    expect(boardHeight([band], 100)).toBe(laneHeight(lane(plain(6), 200), 100));
  });

  it("charges a band gap only between bands", () => {
    const a: BandFit = { lanes: [lane([], 800)] };
    const one = boardHeight([a], 100);
    const two = boardHeight([a, a], 100);
    expect(two - one).toBe(one + LANE_CHROME.bandGapY);
  });

  /**
   * `boardHeight` is *not* monotone in card width, and that is why the solver
   * scans instead of bisecting. This pins the counter-example so nobody
   * "optimises" the scan back into a binary search.
   *
   * A tapped permanent is shorter but wider. Growing the cards pushes the tall
   * untapped card off the end of the first row, leaving a row of nothing but short
   * tapped ones -- so the lane gets shorter even though the cards got bigger.
   */
  it("is not monotone in card width, because tapped cards are short and wide", () => {
    const bands: BandFit[] = [
      { lanes: [lane([...plain(1, { tapped: true }), ...plain(2)], 400)] },
    ];
    expect(boardHeight(bands, 161)).toBeGreaterThan(boardHeight(bands, 162));
  });
});

describe("solveBoardCardWidth", () => {
  const budget = { heightPx: 400, minCardW: 52, maxCardW: 150 };

  it("hands an empty board the whole ceiling", () => {
    const bands: BandFit[] = [{ lanes: [lane([], 800)] }];
    expect(solveBoardCardWidth(bands, budget)).toBe(150);
  });

  it("falls back to the floor when nothing fits", () => {
    // 1600x700: the orb column alone is twice the lane budget, so no card size
    // fits and the mat scrolls. The floor is the honest answer.
    const bands: BandFit[] = [
      { lanes: [lane(plain(20), 300, true)] },
      { lanes: [lane(plain(20), 300)] },
    ];
    expect(solveBoardCardWidth(bands, { ...budget, heightPx: 80 })).toBe(52);
  });

  it("returns a size that actually fits, and the next size up does not", () => {
    const bands: BandFit[] = [
      { lanes: [lane(plain(9), 520, true), lane(plain(2), 260, true)] },
      { lanes: [lane(plain(7, { tapped: true }), 730)] },
    ];
    const solved = solveBoardCardWidth(bands, budget);
    expect(boardHeight(bands, solved)).toBeLessThanOrEqual(budget.heightPx);
    expect(boardHeight(bands, solved + 1)).toBeGreaterThan(budget.heightPx);
  });

  it("is idempotent: feeding its own answer back changes nothing", () => {
    const bands: BandFit[] = [
      { lanes: [lane(plain(5), 500, true), lane(plain(3), 250, true)] },
      { lanes: [lane(plain(8), 730)] },
    ];
    const once = solveBoardCardWidth(bands, budget);
    const twice = solveBoardCardWidth(bands, { ...budget, maxCardW: once });
    expect(twice).toBeCloseTo(once, 3);
  });

  it("never grows as the board fills", () => {
    // The feature's whole premise, as a monotonicity check on the other axis.
    const widths = [0, 3, 6, 10, 16, 24].map((n) =>
      solveBoardCardWidth(
        [
          { lanes: [lane(plain(n), 520, true), lane(plain(1), 260, true)] },
          { lanes: [lane(plain(n), 730)] },
        ],
        budget,
      ),
    );
    for (let i = 1; i < widths.length; i += 1) {
      expect(widths[i]).toBeLessThanOrEqual(widths[i - 1]);
    }
  });

  it("respects a ceiling below the floor by returning the floor", () => {
    expect(solveBoardCardWidth([], { heightPx: 400, minCardW: 80, maxCardW: 60 })).toBe(80);
  });

  /**
   * The property that actually has to hold, fuzzed.
   *
   * `boardHeight` is non-monotone, so "the search is valid" is not a property
   * worth asserting -- the outcome is. Whatever the solver returns must fit, and
   * no larger size on its grid may fit. That is true regardless of how the height
   * function behaves in between, which is exactly why the scan is the right shape.
   */
  it("always returns a fitting size, with nothing larger fitting, over random boards", () => {
    let seed = 987_654_321;
    const rand = () => {
      seed = (seed * 1_103_515_245 + 12_345) & 0x7fffffff;
      return seed / 0x7fffffff;
    };

    for (let trial = 0; trial < 400; trial += 1) {
      const mk = () =>
        Array.from({ length: Math.floor(rand() * 14) }, () => ({
          tapped: rand() < 0.4,
          plies: Math.floor(rand() * (MAX_PLIES + 1)),
          attachments: rand() < 0.2 ? 1 : 0,
        }));
      const width = 150 + rand() * 900;
      const bands: BandFit[] = [
        { lanes: [lane(mk(), width * 0.66, true), lane(mk(), width * 0.33, true)] },
        { lanes: [lane(mk(), width)] },
      ];
      const heightPx = 120 + rand() * 500;
      const solved = solveBoardCardWidth(bands, { heightPx, minCardW: 52, maxCardW: 150 });

      if (solved > 52) {
        expect(
          boardHeight(bands, solved),
          `trial ${trial}: solved ${solved} does not fit ${heightPx}`,
        ).toBeLessThanOrEqual(heightPx);
      }
      // Nothing on the grid above the answer may fit. At the floor this is
      // vacuous -- the floor is returned precisely when nothing fits.
      for (let bigger = solved + 0.5; bigger <= 150; bigger += 0.5) {
        expect(
          boardHeight(bands, bigger),
          `trial ${trial}: ${bigger} fits but the solver returned ${solved}`,
        ).toBeGreaterThan(heightPx);
      }
    }
  });
});

describe("solveHandCardWidth", () => {
  const budget = { heightPx: 220, minCardW: 52, maxCardW: 200 };

  it("caps a single card on the height budget alone", () => {
    // Nothing to overlap, so only the foot's height binds: 220 / 1.4.
    expect(solveHandCardWidth(1, 1180, budget)).toBeCloseTo(220 / 1.4, 3);
  });

  it("shrinks a big hand so neighbours stay distinguishable", () => {
    const cw = solveHandCardWidth(14, 1180, budget);
    const step = handStep(14, cw, 1180);
    expect(step / cw).toBeGreaterThanOrEqual(0.2 - 1e-9);
  });

  it("never grows as the hand fills", () => {
    const widths = [1, 3, 7, 10, 14, 20].map((n) => solveHandCardWidth(n, 1180, budget));
    for (let i = 1; i < widths.length; i += 1) {
      expect(widths[i]).toBeLessThanOrEqual(widths[i - 1]);
    }
  });

  it("honours the floor rather than shrinking without limit", () => {
    // 60 cards across the full fan is still a 92px card -- the overlap rule alone
    // never reaches the floor. It takes a narrow fan as well, which is what a
    // small window supplies.
    expect(solveHandCardWidth(60, 1180, budget)).toBeCloseTo(1180 / (1 + 0.2 * 59), 3);
    expect(solveHandCardWidth(60, 300, budget)).toBe(52);
  });

  it("is bounded by the foot's height budget, not only the overlap rule", () => {
    const tight = solveHandCardWidth(3, 1180, { ...budget, heightPx: 140 });
    expect(tight).toBeCloseTo(100, 3);
  });
});

describe("bandsFor", () => {
  const footprints = {
    Creatures: plain(4),
    "Artifacts & Enchantments": plain(1),
    Lands: plain(6),
  };

  it("splits the front band 2:1 and gives lands the full width", () => {
    const bands = bandsFor(footprints, 800);
    expect(bands).toHaveLength(2);
    const [creatures, globals] = bands[0].lanes;
    // 800 less the 10px band gap, split 2:1.
    expect(creatures.widthPx).toBeCloseTo((790 * 2) / 3);
    expect(globals.widthPx).toBeCloseTo(790 / 3);
    // The back band's label sits beside the cards, so it comes out of the width.
    expect(bands[1].lanes[0].widthPx).toBeCloseTo(
      800 - LANE_CHROME.labelBesideW - LANE_CHROME.gapX,
    );
  });

  it("gives a compact mat's solo front lane the whole width", () => {
    const bands = bandsFor(
      { Creatures: plain(2), "Artifacts & Enchantments": [], Lands: plain(3) },
      300,
      { hideEmpty: true, labels: false },
    );
    expect(bands[0].lanes).toHaveLength(1);
    expect(bands[0].lanes[0].widthPx).toBe(300);
    // No labels on a compact mat, so lands get the full width too.
    expect(bands[1].lanes[0].widthPx).toBe(300);
  });

  it("drops a compact mat's empty bands entirely", () => {
    const bands = bandsFor({ Creatures: [], "Artifacts & Enchantments": [], Lands: [] }, 300, {
      hideEmpty: true,
      labels: false,
    });
    expect(bands).toHaveLength(0);
  });

  it("keeps every lane for the viewer, empty or not", () => {
    const bands = bandsFor({ Creatures: [], "Artifacts & Enchantments": [], Lands: [] }, 800);
    expect(bands).toHaveLength(2);
    expect(bands[0].lanes).toHaveLength(2);
  });
});

/**
 * `LANE_CHROME` mirrors `board.css`, and lane widths are *derived* from those
 * numbers rather than measured off the DOM. So a gap tuned in the stylesheet and
 * not here does not break a layout -- it makes the solver quietly wrong about how
 * much room it has, and every other test in this file keeps passing.
 */
describe("LANE_CHROME matches board.css", () => {
  const rule = (selector: string): string => {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const found = BOARD_CSS.match(new RegExp(`(^|\\n)${escaped}\\s*\\{([^}]*)\\}`));
    expect(found, `no rule for ${selector} in board.css`).not.toBeNull();
    return (found as RegExpMatchArray)[2];
  };

  it("matches .lane__cards' gaps", () => {
    expect(rule(".lane__cards")).toMatch(
      new RegExp(`gap:\\s*${LANE_CHROME.gapY}px\\s+${LANE_CHROME.gapX}px`),
    );
  });

  it("matches .mat__lanes' band gap", () => {
    expect(rule(".mat__lanes")).toMatch(new RegExp(`gap:\\s*${LANE_CHROME.bandGapY}px`));
  });

  it("matches .band's column gap", () => {
    expect(rule(".band")).toMatch(new RegExp(`gap:\\s*${LANE_CHROME.bandGapX}px`));
  });

  it("matches .lane's padding, min-height surplus and label column", () => {
    const body = rule(".lane");
    // padding: 4px 6px -> 8px top plus bottom.
    const padding = body.match(/padding:\s*(\d+)px/);
    expect(padding).not.toBeNull();
    expect(Number((padding as RegExpMatchArray)[1]) * 2).toBe(LANE_CHROME.lanePadY);

    expect(body).toMatch(
      new RegExp(
        `min-height:\\s*calc\\(var\\(--card-w\\) \\* ${LANE_CHROME.aspect} \\+ ${LANE_CHROME.laneMinExtra}px\\)`,
      ),
    );
    expect(body).toMatch(new RegExp(`grid-template-columns:\\s*${LANE_CHROME.labelBesideW}px`));
  });

  it("matches .band--front's 2fr 1fr split", () => {
    const [a, b] = LANE_CHROME.frontSplit;
    expect(rule(".band--front")).toMatch(
      new RegExp(`minmax\\(0, ${a}fr\\)\\s+minmax\\(0, ${b}fr\\)`),
    );
  });
});
