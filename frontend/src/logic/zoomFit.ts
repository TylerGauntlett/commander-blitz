/**
 * How big a card should be, given how many there are.
 *
 * `cardSize.ts` answers "how big is a card in this zone" as a fixed ratio of the
 * viewport-driven base. That is one size for the whole game, so a turn-one board
 * holding two lands renders exactly as small as a turn-fifteen board holding
 * twenty permanents. Early game wastes the screen; late game overflows it.
 *
 * This module answers the other half: **the largest card whose wrapped rows still
 * fit the space actually available.** Measured, not tabulated -- a count->ratio
 * lookup has no idea whether slack exists, and the slack turns out to be wildly
 * viewport-dependent. Measured off the running board with an empty battlefield:
 *
 *   2560x1278   budget 584px, content 475px  -> grows to the 150px ceiling
 *   1600x950    budget 305px, content 304px  -> cannot grow at all
 *   1600x700    budget 160px, content 201px  -> shrinks to the 52px floor
 *
 * No function of card count distinguishes those three. And the direction reverses
 * between them, which is the other reason a table cannot do this: the same feature
 * has to grow the board by a third on a big display and shrink it by a quarter on a
 * short one.
 *
 * Everything here is pure. There is no DOM and no React, which is what lets the
 * awkward part -- flex-wrap arithmetic -- be unit tested without a layout engine,
 * since jsdom has none to offer.
 *
 * The caller supplies the measurements. `state/useZoomFit.ts` owns that, and owns
 * the rule about which measurements are safe to take.
 */

import type { CardView, GameView } from "../api/types";
import { ATTACH_X_RATIO, ATTACH_Y_RATIO, MAX_PLIES, PLY_X } from "./cardStackGeometry";
import { type CardStackGroup, splitActionable, stackCards } from "./stacking";
import { type Lane as LaneName, attachmentsFor, groupBattlefield } from "./zoneGrouping";

/**
 * One wrappable item, as `flex-wrap` sees it.
 *
 * A `CardStack` is not a card-sized box. A tapped permanent lies on its side, a
 * stack of identical ones peeks its plies out to the right, and a host carries
 * its auras stepped down and across. `CardStack` already computes all three
 * (see `closedWidth` / `closedHeight` there); this is the same geometry expressed
 * as the inputs rather than the result, so it can be evaluated at a card width
 * nothing has rendered at yet.
 */
export interface GroupFootprint {
  /** Lying on its side: width and height swap. */
  tapped: boolean;
  /** Visible plies behind the top card, already capped at `MAX_PLIES`. */
  plies: number;
  /** Auras and equipment tucked under this permanent. */
  attachments: number;
}

/** One lane's contents and the width it has to wrap them into. */
export interface LaneFit {
  groups: GroupFootprint[];
  /**
   * The lane's inner width in px.
   *
   * Grid-derived (`minmax(0, 1fr)` all the way down) and so independent of card
   * width, which is the only reason it is safe to feed back in here. Lane
   * *height* depends on card width and must never appear as an input.
   */
  widthPx: number;
  /**
   * Front-band lanes put the label above the cards rather than beside them
   * (`board.css`, `.band--front .lane`), which costs a line of height instead of
   * a column of width.
   */
  labelAbove: boolean;
}

/** One horizontal strip of a mat. Its height is the tallest lane in it. */
export interface BandFit {
  lanes: LaneFit[];
}

export interface FitBudget {
  /** Height the bands must fit inside. */
  heightPx: number;
  minCardW: number;
  maxCardW: number;
}

/**
 * The pieces of a lane's box that are not cards, in px.
 *
 * Every number mirrors a declaration in `board.css`, and `tests/zoomFit.test.ts`
 * parses that file to catch the two drifting apart -- the same trick
 * `tests/palette.test.ts` uses to pin the mana-pip clamp. Getting one of these
 * wrong does not throw; it just makes the solver confidently wrong about how much
 * room it has, which is the failure mode a test has to catch instead of a type.
 */
export interface LaneChrome {
  /** `.lane__cards` column-gap. */
  gapX: number;
  /** `.lane__cards` row-gap. */
  gapY: number;
  /** `.band` column-gap, between the two front lanes. */
  bandGapX: number;
  /** `.mat__lanes` gap, between the front band and the back one. */
  bandGapY: number;
  /** `.lane` padding, top plus bottom. */
  lanePadY: number;
  /** `.lane`'s own `min-height` surplus over one card: the `+ 12px`. */
  laneMinExtra: number;
  /**
   * The label row plus `.band--front .lane`'s 4px gap, when the label sits above
   * the cards rather than beside them.
   */
  labelAboveH: number;
  /** `.lane`'s label column, when it sits beside them. */
  labelBesideW: number;
  /** `.band--front`'s `2fr 1fr` split. */
  frontSplit: readonly [number, number];
  /** A card is this many times its width tall. */
  aspect: number;
}

/**
 * Measured off the rendered board, not guessed.
 *
 * `labelAboveH` is the one that had to be measured, and the first attempt at it
 * was wrong in a way worth recording. Subtracting a front lane's height from a
 * back lane's gave 19px, which looked like the label -- but the back lane was
 * pinned to its own `min-height` at the time, so the difference was measuring two
 * different things. Read off the rendered box instead, the label row plus
 * `.band--front .lane`'s 4px gap is 23px, and 23 is what reproduces the real lane
 * heights at every viewport (see `tests/zoomFit.test.ts`, "matches the real
 * rendered lane heights").
 */
export const LANE_CHROME: LaneChrome = {
  gapX: 12,
  gapY: 10,
  bandGapX: 10,
  bandGapY: 12,
  lanePadY: 8,
  laneMinExtra: 12,
  labelAboveH: 23,
  labelBesideW: 74,
  frontSplit: [2, 1],
  aspect: 1.4,
};

/**
 * The parts of a *mat* that are not lanes.
 *
 * The solver is handed lane widths and a height budget, and something has to turn
 * a measured container into those. Deriving them arithmetically rather than
 * measuring the lanes keeps every ref inside `Table` -- no ref has to be threaded
 * down through `PlayerMat` -- at the price of these numbers having to match
 * `board.css`. `tests/zoomFit.test.ts` parses the stylesheet to hold them to it.
 *
 * The orb column is deliberately *not* something the zoom can spend. It is 190px
 * of fixed furniture on the viewer's mat and 112px on a compact one, and at
 * 1600x950 it is also the tallest thing on the mat -- taller than the lanes it
 * sits beside. That is the real ceiling on this whole feature, and shrinking it is
 * a separate change.
 */
export interface MatChrome {
  /** `.mat` grid column 1: the orb. */
  sideW: number;
  /** `.mat` column gap. */
  colGap: number;
  /** `.mat` padding, left plus right. */
  padX: number;
  /** `.mat` padding, top plus bottom. */
  padY: number;
  /** `.mat` border, one side plus the other. */
  border: number;
  /**
   * Whether this mat renders lane labels at all. A compact mat hides them
   * (`.mat--compact .lane__label { display: none }`), which is why its front band
   * costs no label line and its back band gives up no label column.
   */
  labels: boolean;
}

export const VIEWER_MAT: MatChrome = {
  sideW: 190,
  colGap: 10,
  padX: 16,
  padY: 16,
  border: 2,
  labels: true,
};

/** A compact mat gives up the width first, and hides its labels entirely. */
export const COMPACT_MAT: MatChrome = {
  sideW: 112,
  colGap: 6,
  padX: 12,
  padY: 12,
  border: 2,
  labels: false,
};

/** The width a mat's lanes get, inside a container of this client width. */
export function lanesWidthIn(containerW: number, chrome: MatChrome): number {
  return Math.max(0, containerW - chrome.border - chrome.sideW - chrome.colGap - chrome.padX);
}

/** The height a mat's lanes get, inside a container of this client height. */
export function lanesHeightIn(containerH: number, chrome: MatChrome): number {
  return Math.max(0, containerH - chrome.border - chrome.padY);
}

/** A card's own box at this width, before plies and attachments. */
function cardBox(footprint: GroupFootprint, cardW: number, aspect: number) {
  const w = footprint.tapped ? cardW * aspect : cardW;
  const h = footprint.tapped ? cardW : cardW * aspect;
  return { w, h };
}

/**
 * The width and height one group occupies, at this card width.
 *
 * Mirrors `CardStack`'s `closedWidth` / `closedHeight`. The attachment offsets
 * are ratios of the card, so they scale; the plies are a flat 7px each and do
 * not, which is why they are added rather than multiplied.
 */
export function groupBox(
  footprint: GroupFootprint,
  cardW: number,
  chrome: LaneChrome = LANE_CHROME,
): { w: number; h: number } {
  const { w, h } = cardBox(footprint, cardW, chrome.aspect);
  return {
    w: w + footprint.plies * PLY_X + footprint.attachments * cardW * ATTACH_X_RATIO,
    h: h + footprint.attachments * cardW * ATTACH_Y_RATIO,
  };
}

/**
 * The rows `flex-wrap` would produce, and how tall each one is.
 *
 * Greedy first-fit by line, which is exactly what `flex-wrap: wrap` does -- so
 * this is the real answer rather than an estimate. `floor(laneW / cardW)` would
 * be an estimate, and a bad one: a lane holding six tapped lands (landscape, 1.4x
 * as wide) packs nothing like a lane holding six untapped ones, and a lane mixing
 * the two packs like neither.
 *
 * A group wider than the whole lane still gets its own row rather than looping
 * forever -- that is what the browser does with an unshrinkable flex item too.
 */
export function wrapRowHeights(
  lane: LaneFit,
  cardW: number,
  chrome: LaneChrome = LANE_CHROME,
): number[] {
  const rows: number[] = [];
  let used = 0;
  let tallest = 0;

  for (const footprint of lane.groups) {
    const box = groupBox(footprint, cardW, chrome);
    const needs = used === 0 ? box.w : used + chrome.gapX + box.w;
    if (used > 0 && needs > lane.widthPx) {
      rows.push(tallest);
      used = box.w;
      tallest = box.h;
    } else {
      used = needs;
      tallest = Math.max(tallest, box.h);
    }
  }
  if (used > 0) rows.push(tallest);
  return rows;
}

/** How many rows this lane wraps onto. */
export function wrapRows(
  lane: LaneFit,
  cardW: number,
  chrome: LaneChrome = LANE_CHROME,
): number {
  return wrapRowHeights(lane, cardW, chrome).length;
}

/**
 * A lane's outer height at this card width.
 *
 * **There are two independent floors here, and missing the second one was a real
 * bug.** `.lane__cards` carries `min-height: calc(var(--card-w) * 1.4)` and `.lane`
 * carries `min-height: calc(var(--card-w) * 1.4 + 12px)` -- and they are not the
 * same constraint wearing two hats. In the *front* band the label sits above the
 * cards box, so the cards' floor and the label stack on top of each other and
 * together exceed the lane's own floor: an empty front lane is `1.4w + 23 + 8`,
 * not `1.4w + 12`. Modelling only the lane's floor under-counted every front lane
 * by 19px, which let the solver pick a card size whose lanes then overflowed the
 * budget it had just fitted them into.
 *
 * Both floors are also what make an empty lane cost a whole card -- the reserved
 * slot that stops the viewer's board jumping as permanents come and go.
 */
export function laneHeight(
  lane: LaneFit,
  cardW: number,
  chrome: LaneChrome = LANE_CHROME,
): number {
  const rows = wrapRowHeights(lane, cardW, chrome);
  const packed =
    rows.reduce((sum, h) => sum + h, 0) + Math.max(0, rows.length - 1) * chrome.gapY;
  // `.lane__cards` never collapses below one card, however little is in it.
  const cards = Math.max(cardW * chrome.aspect, packed);
  const label = lane.labelAbove ? chrome.labelAboveH : 0;
  const laneFloor = cardW * chrome.aspect + chrome.laneMinExtra;
  return Math.max(laneFloor, cards + label + chrome.lanePadY);
}

/** Every band stacked, at this card width. */
export function boardHeight(
  bands: BandFit[],
  cardW: number,
  chrome: LaneChrome = LANE_CHROME,
): number {
  if (bands.length === 0) return 0;
  const heights = bands.map((band) =>
    band.lanes.reduce((tallest, lane) => Math.max(tallest, laneHeight(lane, cardW, chrome)), 0),
  );
  return (
    heights.reduce((sum, h) => sum + h, 0) + Math.max(0, bands.length - 1) * chrome.bandGapY
  );
}

/**
 * Granularity of the search, in px. Half a pixel of card width is invisible, and
 * a 52..150 range is ~200 evaluations of some arithmetic over a dozen groups --
 * cheap enough to do on a state change and not worth being clever about.
 */
const SEARCH_STEP = 0.5;

/**
 * The largest card width whose bands fit the budget.
 *
 * A descending scan, and **not** a binary search, because `boardHeight` is not
 * monotone in `cardW`. That is worth explaining, because it is surprising and a
 * binary search over it fails silently rather than loudly:
 *
 * A tapped permanent lies on its side, so it is *shorter but wider* than an
 * untapped one. Growing the cards can therefore push a tall untapped card off the
 * end of a row and leave a row of nothing but short tapped ones behind it -- which
 * makes the lane briefly **shorter** than it was at the smaller card size. At a
 * 400px lane holding [tapped, untapped, untapped], a 161px card packs
 * `[tapped, untapped]` then `[untapped]` for 450.8px, and a 162px card packs
 * `[tapped]` then `[untapped, untapped]` for 388.8px. Bisection assumes it can
 * discard everything above a size that fits; here that is untrue, and it would
 * return a card size that overflows.
 *
 * The scan takes the first size that fits from the top, so it is right whatever
 * the function does in between. `tests/zoomFit.test.ts` asserts the outcome
 * directly -- what it returns fits, and nothing larger on the grid does.
 *
 * Returns `minCardW` when even that overflows. That is the honest answer, not a
 * failure: `.play__mine` scrolls, and at 1600x700 the orb column alone is twice
 * the whole budget, so no card size fits and pretending otherwise would just mean
 * lying about which pixel the overflow starts at.
 */
export function solveBoardCardWidth(
  bands: BandFit[],
  budget: FitBudget,
  chrome: LaneChrome = LANE_CHROME,
): number {
  const { minCardW, maxCardW } = budget;
  if (maxCardW <= minCardW) return minCardW;
  for (let cw = maxCardW; cw > minCardW; cw -= SEARCH_STEP) {
    if (boardHeight(bands, cw, chrome) <= budget.heightPx) return cw;
  }
  return minCardW;
}

/**
 * How wide the fan may grow before cards start overlapping harder.
 *
 * A cap rather than `100%`: a two-card hand spread across 1400px reads as two
 * unrelated cards, not as a hand. `HandFan` imports this rather than keeping its
 * own copy -- the solver has to reason about the same fan the component draws, and
 * a first pass at this file had the step as a *ratio* of the card while the
 * component used a flat pixel spread. Two definitions of one number is how the
 * solver ends up confidently describing a layout that does not exist.
 */
export const HAND_FAN_W = 1180;

/** Cards overlap once the hand is wider than this. */
export const HAND_MAX_SPREAD = 118;

/**
 * How much of each hand card must stay uncovered by its neighbour.
 *
 * A hand is only readable if you can tell where one card stops and the next
 * begins. Below about a fifth of a card the fan reads as a single striped object,
 * which is the thing growing the cards would otherwise buy at the hand's expense.
 */
const HAND_MIN_VISIBLE_RATIO = 0.2;

/**
 * The hand solves closed-form, not by search.
 *
 * The fan never wraps -- its slots are absolutely positioned and overlap instead
 * (`HandFan`) -- so the constraint is algebraic:
 *
 *   step(cw) = min(MAX_SPREAD_RATIO * cw, (fanW - cw) / (count - 1))
 *   require   step >= MIN_VISIBLE_RATIO * cw
 *   =>        cw <= fanW / (1 + MIN_VISIBLE_RATIO * (count - 1))
 *
 * and separately `cw <= heightBudget / aspect`. The first term is what stops a
 * fifteen-card hand growing until it is a solid band; the second is what stops
 * any hand eating the board's row.
 */
export function solveHandCardWidth(
  count: number,
  fanWidthPx: number,
  budget: FitBudget,
  aspect: number = LANE_CHROME.aspect,
): number {
  const byHeight = budget.heightPx / aspect;
  const fanW = Math.min(fanWidthPx, HAND_FAN_W);
  const byWidth =
    count > 1 ? fanW / (1 + HAND_MIN_VISIBLE_RATIO * (count - 1)) : Number.POSITIVE_INFINITY;
  const wanted = Math.min(byHeight, byWidth, budget.maxCardW);
  return Math.max(budget.minCardW, wanted);
}

/**
 * The pitch between hand slots. The single definition of the fan's spacing --
 * `HandFan` calls this rather than repeating the formula.
 */
export function handStep(count: number, cardW: number, fanWidthPx: number): number {
  if (count <= 1) return 0;
  const fanW = Math.min(fanWidthPx, HAND_FAN_W);
  return Math.min(HAND_MAX_SPREAD, (fanW - cardW) / (count - 1));
}

// ------------------------------------------------------------------ adapters

/**
 * The footprints one player's lanes would render, lane by lane.
 *
 * Reuses the grouping the board itself uses -- `groupBattlefield` +
 * `attachmentsFor` for the lanes, then `stackCards` + `splitActionable` for the
 * stacks -- because the unit that wraps is a *group*, not a card. Twelve basics
 * are one box, and a solver counting twelve would shrink the board to fit a lane
 * that was never crowded.
 *
 * This repeats work `Lane` does on render. It is pure and cheap, and the
 * alternative -- hoisting `stackCards` up into `PlayerMat` and passing groups
 * down -- changes `Lane`'s prop contract and the tests written against it. Worth
 * doing, separately, if this ever shows up in a profile.
 */
export function footprintsFor(
  state: GameView,
  pid: number,
  actionableOids: ReadonlySet<number>,
): Record<LaneName, GroupFootprint[]> {
  const lanes = groupBattlefield(state, pid);
  const attachments = attachmentsFor(state, pid);
  const of = (cards: CardView[]) =>
    stackCards(cards, attachments)
      .flatMap((group) => splitActionable(group, actionableOids))
      .map(footprintOf);
  return {
    Creatures: of(lanes.Creatures),
    "Artifacts & Enchantments": of(lanes["Artifacts & Enchantments"]),
    Lands: of(lanes.Lands),
  };
}

/** One rendered stack, as the solver needs it. */
export function footprintOf(group: CardStackGroup): GroupFootprint {
  return {
    tapped: group.top.tapped === true,
    plies: Math.min(group.count - 1, MAX_PLIES),
    attachments: group.attachments.length,
  };
}

/**
 * The two bands a mat renders, given its lane contents and inner width.
 *
 * The front band carries creatures beside the global artifacts and enchantments,
 * split `2fr 1fr`; the back band carries lands at full width. `mirrored` only
 * flips which is drawn first, so it does not change any height and is not a
 * parameter here.
 *
 * `hideEmpty` is the compact mat's rule (`PlayerMat`'s `visible`): an opponent's
 * empty lane is not rendered at all, and a front band down to one lane takes the
 * whole width (`.band--solo`).
 */
export function bandsFor(
  footprints: Record<LaneName, GroupFootprint[]>,
  lanesWidthPx: number,
  options: { hideEmpty?: boolean; labels?: boolean; chrome?: LaneChrome } = {},
): BandFit[] {
  const chrome = options.chrome ?? LANE_CHROME;
  const hideEmpty = options.hideEmpty ?? false;
  const labels = options.labels ?? true;
  const [a, b] = chrome.frontSplit;

  const front: LaneName[] = ["Creatures", "Artifacts & Enchantments"];
  const shownFront = hideEmpty ? front.filter((lane) => footprints[lane].length > 0) : front;
  const shownBack = hideEmpty && footprints.Lands.length === 0 ? [] : (["Lands"] as LaneName[]);

  const bands: BandFit[] = [];

  if (shownFront.length > 0) {
    const solo = shownFront.length === 1;
    const inner = solo ? lanesWidthPx : lanesWidthPx - chrome.bandGapX;
    const share = (lane: LaneName) => {
      if (solo) return inner;
      return lane === "Creatures" ? (inner * a) / (a + b) : (inner * b) / (a + b);
    };
    bands.push({
      lanes: shownFront.map((lane) => ({
        groups: footprints[lane],
        // A compact mat hides its labels entirely, so the front band's label line
        // costs nothing there.
        widthPx: share(lane),
        labelAbove: labels,
      })),
    });
  }

  if (shownBack.length > 0) {
    bands.push({
      lanes: [
        {
          groups: footprints.Lands,
          // The back band's label sits *beside* the cards, taking a column
          // rather than a line -- so it comes out of the width, not the height.
          widthPx: labels ? lanesWidthPx - chrome.labelBesideW - chrome.gapX : lanesWidthPx,
          labelAbove: false,
        },
      ],
    });
  }

  return bands;
}
