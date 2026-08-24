/**
 * The front door's row of cards, as arithmetic.
 *
 * Ported from `mockups/door/_door.js`. One continuous number in -- `s`, where
 * the selection currently is in card-index space -- and one pose per card out.
 * Nothing here is keyframed and nothing is a discrete state, so a card
 * mid-flight is at a real position rather than at a tween between two poses.
 *
 *     d = i - s
 *     x      (i-1)*STEP + sign(d) * (PUSH*min(|d|,1) - BUNCH*max(0,|d|-1))
 *     y      DROOP*min(|d|,TILT) - LIFT*max(0, 1-|d|)
 *     rot    clamp(d, -TILT, TILT) * ARC
 *     scale  1 + RAISE*max(0, 1-|d|)
 *     z      100 - round(|d|*10)
 *     ink    1 - clamp((|d| - 1) / 0.6)
 *
 * `ARC`, the push-away and the parabolic droop are `HandFan.tsx:37-83`'s, which
 * is the same mechanic on the board and already tuned. **THE `BUNCH` TERM IS
 * THE ONLY NEW ARITHMETIC**: `PUSH` alone spreads the row evenly, which is a
 * fan; subtracting `BUNCH` once a card is more than one place from the
 * selection pulls the far card back *over* its neighbour, so selecting an end
 * leaves one clear card and a pair -- which is what a hand of cards actually
 * does when you pull one out of it. A hand of seven has no far side, which is
 * why `HandFan` has no such term.
 *
 * `ink` is the round's second finding rather than a nicety. One place from the
 * selection a card is on top of everything and can carry whatever it likes; TWO
 * places and it is under its own neighbour, so everything except the outer
 * sliver is gone -- and a sentence that runs into a covering card does not read
 * as hidden, it reads as TRUNCATED, which is worse, because a truncated line
 * looks like a bug in the copy. So the stack costs a card everything except its
 * name, and the line under the name fades out with it.
 */

export interface DoorTune {
  /** px between neighbouring cards at rest */
  STEP: number;
  /** px a neighbour slides away from the selected card */
  PUSH: number;
  /**
   * px the FAR card is pulled back over its neighbour.
   *
   * NOT A TASTE -- bounded by the longest label. Of two cards on the same side
   * of the selection the nearer is drawn on top, so what is left of the further
   * one is a strip `STEP - BUNCH` wide, and its name has to fit in that strip or
   * it cannot be read at any alignment. The mockup measured it: at 112 the far
   * card's centred DECKS runs 10.4px under its neighbour; it reaches zero at
   * 100; 96 leaves 4px of margin, which is what a different font stack on a
   * different machine is worth.
   */
  BUNCH: number;
  /** degrees of tilt per place from the selection */
  ARC: number;
  /** px the selected card rises */
  LIFT: number;
  /** px an unselected card sits below it */
  DROOP: number;
  /** fraction the selected card grows */
  RAISE: number;
  /** places at which the tilt stops growing */
  TILT: number;
}

/**
 * The tune, at the 1280x800 the mockup was authored on.
 *
 * The five px terms are multiplied by the stage's scale before use (see
 * `scaleTune`), so the composition is the same shape on a Deck and on a 2560px
 * monitor rather than three cards adrift in the middle of a large screen.
 */
export const DOOR_TUNE: DoorTune = {
  STEP: 248,
  PUSH: 36,
  BUNCH: 96,
  ARC: 4.5,
  LIFT: 26,
  DROOP: 14,
  RAISE: 0.1,
  TILT: 1.6,
};

/** The tune at a given stage scale. The two unitless terms do not scale. */
export function scaleTune(tune: DoorTune, scale: number): DoorTune {
  return {
    ...tune,
    STEP: tune.STEP * scale,
    PUSH: tune.PUSH * scale,
    BUNCH: tune.BUNCH * scale,
    LIFT: tune.LIFT * scale,
    DROOP: tune.DROOP * scale,
  };
}

export interface DoorPose {
  x: number;
  y: number;
  rot: number;
  scale: number;
  z: number;
  /** How much of this card is still worth printing on: 1 clear, 0 buried. */
  ink: number;
}

const clamp01 = (n: number) => (n < 0 ? 0 : n > 1 ? 1 : n);

/**
 * Card `i`'s pose when the selection is at `s`, in a row of `count`.
 *
 * `count` DEFAULTS TO THREE because that is the row this arithmetic was authored
 * and measured against, and defaulting keeps `tests/doorRow.test.ts` -- which
 * pins the original composition to the pixel -- calling it the way it always
 * did. Both terms that depend on it below are identities at three.
 */
export function poseOf(i: number, s: number, tune: DoorTune, count = 3): DoorPose {
  const d = i - s;
  const a = Math.abs(d);
  const sign = d < 0 ? -1 : d > 0 ? 1 : 0;
  const near = Math.min(a, 1);
  /*
   * CLAMPED, and it was not, which was a bug waiting for a fourth card.
   *
   * `BUNCH` pulls a far card back OVER its neighbour, and its docstring above
   * measures the readable strip that leaves -- at one place out. In a row of
   * three nothing is ever more than one place out from a selected end, so the
   * unbounded form was correct by accident. At four, a card three places from
   * the selection took `BUNCH * 2` of pull-back and slid clean through the card
   * it was supposed to hide behind, inverting the stack.
   */
  const far = Math.min(1, Math.max(0, a - 1));
  const tilt = Math.max(-tune.TILT, Math.min(tune.TILT, d));
  return {
    // Centred on the row's middle -- index 1 of three, 1.5 of four -- so the
    // selected card sits at x = 0 and the arithmetic is written about a row
    // rather than an edge. An even row has no middle CARD, which is fine: it
    // has a middle, and that is all this needs.
    x: (i - (count - 1) / 2) * tune.STEP + sign * (tune.PUSH * near - tune.BUNCH * far),
    y: tune.DROOP * Math.min(a, tune.TILT) - tune.LIFT * Math.max(0, 1 - a),
    rot: tilt * tune.ARC,
    scale: 1 + tune.RAISE * Math.max(0, 1 - a),
    z: 100 - Math.round(a * 10),
    ink: 1 - clamp01((a - 1) / 0.6),
  };
}

/**
 * How big the stage is, against the 1280x800 the mockup was drawn at.
 *
 * The mockup scales a fixed 1280x800 deck to whatever window is open, which is
 * right for a review surface and wrong for an application: at 1600x950 a scaled
 * deck is a blurry 1280 with letterboxing. Here the room is full-bleed and only
 * the *furniture* scales, off the same number.
 *
 * IT IS EXACTLY 1 AT 1280x800, which is the whole point of stating the number
 * rather than clamping off viewport units: the Deck gets the composition the
 * mockup was measured at, to the pixel. Above that it grows to 1.45 -- past
 * there the row is wider than the pool of light it stands in and the
 * composition comes apart. Below, it shrinks to 0.72 and the *type* does not
 * follow it down: every size on this screen is `max(16px, ...)`, because the
 * 16px floor is a CI gate and a card that shrank its copy would clear the
 * layout by failing the thing the layout is for.
 */
export function stageScale(width: number, height: number): number {
  return Math.max(0.72, Math.min(1.45, Math.min(width / 1280, height / 800)));
}
