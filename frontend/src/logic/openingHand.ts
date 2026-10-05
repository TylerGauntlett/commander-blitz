/**
 * The opening hand's arch, as arithmetic, and which half of a mulligan it is.
 *
 * Ported from the mulligan round's 01 'The Deal' (`docs/design-record.md#mulligan`). The round's whole finding is
 * one number: the mulligan round's probe (`docs/design-record.md#mulligan`) binary-searches a real card in a real
 * browser for the narrowest width at which it can print its own name, cost, type
 * line and rules text at the 16px floor, and the answer for the widest of a
 * seven-card hand is **296px**. Seven of those laid flush is 2072px against a
 * 1280px panel, so a hand you can read all at once is not available at any
 * layout. A hand you can read one card at a time is, and this is its shape.
 *
 * ---------------------------------------------------------------------------
 * NOTHING HERE IS A FUNCTION OF THE SELECTION, and that is the point.
 *
 * The mockup went through three passes and the third is the one that matters.
 * The second grew the selected card from 176px to 296 and closed the other six
 * up around it, which reads correctly in a still and badly in the hand: the row
 * has to be re-centred every time the selection moves, so walking from the first
 * card to the last slid all seven sideways six times. **The one thing holding
 * still was the card you were trying to read, and everything you were reading it
 * against moved underneath it.**
 *
 * So every card is the same size, `handRow` is called once per resize, and
 * moving the selection touches `z-index`, one attribute and one custom property.
 * `slots` deliberately takes no selected index -- there is nowhere for one to go.
 *
 * ---------------------------------------------------------------------------
 * THE STACK FALLS AWAY FROM THE SELECTION IN BOTH DIRECTIONS, which is `zFor`.
 * A one-directional fan with the selected card lifted to the top buries its
 * right-hand neighbour completely: that card is covered on its left by the
 * 296px card in front of it and on its right by the next one along, and what
 * survives is a four-pixel stripe.
 */

import type { GameView } from "../api/types";
import { stageScale } from "./doorRow";

/** Which half of a London mulligan a decision is. */
export type MulliganPhase = "keep" | "bottom";

/**
 * The `purpose` tag the engine puts on the bottoming decision.
 *
 * `engine/game.py` passes it to `ask_objects`, whose own docstring says the tag
 * exists so "agents and the UI branch on it; without it they would have to
 * pattern-match on the human-readable prompt". This is the client half of that
 * bargain, and it is why nothing here reads `pending.prompt`.
 */
export const MULLIGAN_BOTTOM = "mulligan_bottom";

/**
 * Which half of a mulligan this decision is, or `null` if it is not one.
 *
 * The same three guards `isModalDecision` makes -- it has to be a decision, it
 * has to be **yours**, and the game has to still be running -- plus the kind.
 * An opponent mulliganing is not a screen you get; `labels.thinkingLabel`
 * already says "AI 1 — mulligan" in the action panel for that.
 */
export function mulliganPhase(state: GameView): MulliganPhase | null {
  const pending = state.pending;
  if (pending === null || pending.player !== state.seat || state.game_over) return null;
  if (pending.kind === "mulligan") return "keep";
  if (pending.kind === "choose_objects" && pending.context?.purpose === MULLIGAN_BOTTOM) {
    return "bottom";
  }
  return null;
}

/** `STARTING_HAND` in `engine/game.py`: every mulligan draws seven. */
const STARTING_HAND = 7;

/** What the next mulligan, or a keep now, costs. */
export interface MulliganCost {
  /** The next mulligan is one of the free ones: seven back, nothing bottomed. */
  nextIsFree: boolean;
  /** Cards kept if you mulligan once more and then keep. */
  keepAfterNext: number;
  /** Cards that go to the bottom if you keep this hand. */
  bottomIfKept: number;
}

/**
 * The London mulligan's arithmetic with free mulligans taken off the top.
 *
 * `engine/game.py` bottoms `max(0, taken - free)` once you keep, and `free`
 * comes off the wire (`mulligans_free`) so the two cannot disagree.
 */
export function mulliganCost(taken: number, free: number): MulliganCost {
  const paid = (n: number) => Math.max(0, n - free);
  return {
    nextIsFree: taken < free,
    keepAfterNext: Math.max(0, STARTING_HAND - paid(taken + 1)),
    bottomIfKept: paid(taken),
  };
}

/**
 * The tune, at the 1280x800 the mockup was measured on.
 *
 * Every one of these is a number the mulligan round's 01 'The Deal' (`docs/design-record.md#mulligan`) states out
 * loud; the two in degrees are the only ones that do not scale.
 */
export const MULL_TUNE = {
  /** px. `probe.mjs`'s answer, and the reason the round exists. */
  CARD_W: 296,
  /** A card is a 1.4 portrait everywhere in this app. */
  ASPECT: 1.4,
  /** px between neighbouring cards: 6 x 144 + 296 = 1160 on a 1280px stage. */
  PITCH: 144,
  /** px from the top of the stage to the top of an un-sagged slot. */
  ROW_TOP: 100,
  /** px below a slot's own top edge that the arch pivots about. */
  PIVOT: 700,
  /** degrees of tilt per step away from the middle of the row. */
  SPREAD: 0.9,
  /** px of drop per step squared, so the row sits on a curve. */
  SAG: 4,
  /** px the card you are on rises. */
  LIFT: 20,
  /**
   * px a card marked for the bottom sinks.
   *
   * Lived in `opening.css` until the slot itself started carrying the pose. Both
   * displacements are on one transform now -- see `.mull__slot` -- and a
   * transform written inline cannot be overridden by a stylesheet, so the choice
   * between them is arithmetic rather than cascade.
   */
  SINK: 22,
  /** px from the top of the stage to the row of answers. */
  ACTS_TOP: 622,
} as const;

const RAD = Math.PI / 180;

/**
 * How much of the stage the width term is allowed to fill.
 *
 * Solving for the width that fits EXACTLY puts the outer card's corner on the
 * bezel, and `handRow` rounds `left` to a whole pixel, so half the time it puts
 * it a fraction past. A card touching the edge of the panel reads as clipped
 * whether or not it is. One percent each side is the smallest margin that is
 * still visibly a margin, and at 1280x800 the width term is 1.02 against a
 * height term of 1.0 -- so a Deck never reaches this and the number is invisible
 * there.
 */
const EDGE_KEEP = 0.98;

/**
 * How much wider than its own box the outermost card reaches, in card widths.
 *
 * THE TILT IS SMALL BECAUSE THE PIVOT IS FAR, and the mockup got the sum of
 * those two wrong on its first try. A slot's top outer corner sits
 * `hypot(CARD_W/2, PIVOT)` from the pivot -- 715px at a 296px card -- so
 * rotating the end card swings that corner much further than its tilt suggests:
 * 44px at 1.2 degrees per step, against a margin of 48. Both end cards came to
 * rest 4px from the edge of the panel, which is *inside* the stage, so the
 * mockup's own overflow gate passed and only a screenshot showed it.
 *
 * At `SPREAD` 0.9 the swing is 33px against a 60px margin, and this function is
 * what lets a test assert that rather than a reviewer notice it.
 */
export function reachRatio(count: number): number {
  const theta = (MULL_TUNE.SPREAD * Math.max(0, count - 1)) / 2;
  const pivot = MULL_TUNE.PIVOT / MULL_TUNE.CARD_W;
  return 0.5 * Math.cos(theta * RAD) + pivot * Math.sin(theta * RAD);
}

/**
 * The width the whole row needs, in card widths, rotation included.
 *
 * `(count - 1)` pitches between the outermost two slot centres, plus one
 * `reachRatio` at each end. At seven cards this is 4.14, so a 296px card wants
 * 1226px and a Deck has 1280.
 */
export function rowRatio(count: number): number {
  if (count <= 0) return 0;
  const pitch = MULL_TUNE.PITCH / MULL_TUNE.CARD_W;
  return Math.max(0, count - 1) * pitch + 2 * reachRatio(count);
}

/**
 * The scale the composition is drawn at, given a stage and a hand size.
 *
 * `stageScale` is the door's -- exactly 1.0 at 1280x800, clamped to
 * [0.72, 1.45] -- and it is keyed off **height**, because that is what binds on
 * the board and what a Deck fixes. This takes the smaller of that and whatever
 * the stage's *width* can hold, so a tall narrow window shrinks the arch instead
 * of running it off both sides. At 1280x800 the width term is 1.04 and the
 * height term is exactly 1, so the Deck gets the mockup's composition to the
 * pixel and nothing about this function is visible there.
 *
 * The type does not follow it down: every font-size on this screen is
 * `max(16px, ...)`, because the floor is a CI gate and a card that shrank its
 * own copy would clear the layout by failing the thing the layout is for.
 */
export function stageUnit(width: number, height: number, count: number): number {
  const byWidth = (width * EDGE_KEEP) / (MULL_TUNE.CARD_W * rowRatio(count));
  return Math.min(stageScale(width, height), byWidth);
}

/** One slot's box, in stage pixels. */
export interface HandSlot {
  /** Left edge, before rotation. */
  x: number;
  /** Top edge, sag included, relative to the row's own top. */
  y: number;
  /** Degrees, about a pivot `pivot` px below the slot's top edge. */
  rot: number;
}

export interface HandRow {
  cardW: number;
  cardH: number;
  pitch: number;
  /** The row's box, ignoring rotation: what `left` and `width` would be. */
  left: number;
  width: number;
  /** Distance from the top of the stage to the row's own top edge. */
  top: number;
  /** How tall the row's box is: one card plus the outermost card's sag. */
  height: number;
  /** `transform-origin`'s y, in px below a slot's top edge. */
  pivot: number;
  /** px the selected card rises. */
  lift: number;
  /** px a card marked for the bottom sinks. */
  sink: number;
  /**
   * px of slack the slot's hit pad adds above and below its own box.
   *
   * The slot MOVES now -- it carries the lift and the sink itself, so that the
   * ring, which measures the stop, is around the card rather than around where
   * the card used to be. That is the one thing `.mull__lift` was there to avoid:
   * transform the box a pointer is inside and the pointer falls out of it, onto
   * whichever neighbour is under that pixel, whose `mouseenter` moves the
   * selection, which drops this card back under the pointer, forever.
   *
   * So `.mull__slot::after` is a hit pad the size of the slot plus this much at
   * both ends, and it travels with the slot -- which makes the hit region a
   * superset of both poses, and the pointer never leaves the card it is resting
   * on. `HandFan`'s `.hand__slot` is the same trick with the parts the other way
   * round: there the fixed box is the parent and the moving one is the child.
   *
   * The larger of the two displacements, because one pad answers for both.
   */
  pad: number;
  slots: HandSlot[];
}

/**
 * Every slot's box and pose, for a hand of `count` on a stage `width` wide.
 *
 * Called once per resize and never on a selection change. The pose is a pure
 * function of `i - centre`, so the middle card is the upright one and the arch
 * is pinned to the row rather than to whatever you happen to be reading.
 */
export function handRow(count: number, width: number, unit: number): HandRow {
  const cardW = MULL_TUNE.CARD_W * unit;
  const cardH = cardW * MULL_TUNE.ASPECT;
  const pitch = MULL_TUNE.PITCH * unit;
  const rowW = count > 0 ? pitch * (count - 1) + cardW : 0;
  const left = Math.round((width - rowW) / 2);
  const centre = (count - 1) / 2;
  const sag = MULL_TUNE.SAG * unit;

  const slots: HandSlot[] = [];
  for (let i = 0; i < count; i += 1) {
    const d = i - centre;
    slots.push({ x: left + i * pitch, y: d * d * sag, rot: d * MULL_TUNE.SPREAD });
  }

  return {
    cardW,
    cardH,
    pitch,
    left,
    width: rowW,
    top: MULL_TUNE.ROW_TOP * unit,
    height: cardH + centre * centre * sag,
    pivot: MULL_TUNE.PIVOT * unit,
    lift: MULL_TUNE.LIFT * unit,
    sink: MULL_TUNE.SINK * unit,
    pad: Math.max(MULL_TUNE.LIFT, MULL_TUNE.SINK) * unit,
    slots,
  };
}

/**
 * The horizontal extent the row actually occupies, rotation included.
 *
 * What `handRow` reports as `left`/`width` is the row's *boxes*; this is where
 * the ink ends up. The two differ by `reachRatio - 0.5` at each end, which is
 * the 33px the tilt costs at a 296px card -- the whole reason the margin is 60
 * and not 12.
 */
export function rowExtent(row: HandRow, count: number): { left: number; right: number } {
  const reach = reachRatio(count) * row.cardW;
  const centreOfFirst = row.left + row.cardW / 2;
  const centreOfLast = centreOfFirst + row.pitch * Math.max(0, count - 1);
  return { left: centreOfFirst - reach, right: centreOfLast + reach };
}

/**
 * Stacking order, falling away from the card you are on in both directions.
 *
 * Not `i`. A one-directional fan with the selected card lifted to the top leaves
 * its right-hand neighbour a four-pixel stripe -- covered on the left by the
 * card in front of it and on the right by the next one along. Falling away from
 * the selection is also what a real hand does when a thumb pushes one card proud
 * of the others: the cards on the left show their left edges and the ones on the
 * right show their right edges.
 */
export function zFor(index: number, selected: number): number {
  return 100 - Math.abs(index - selected);
}
