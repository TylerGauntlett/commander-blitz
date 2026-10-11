/**
 * The analog repeat ramp, as arithmetic.
 *
 * THE THUMB IS AN ANALOG INPUT AND A FIXED REPEAT RATE THROWS THAT AWAY. A
 * d-pad-style `first = 400ms, next = 95ms` is the same number whether the stick
 * is barely past the fire line or buried in the corner, which is a d-pad
 * wearing a stick -- the extra 45% of travel buys nothing.
 *
 * Every console UI that feels good does it the other way round. A nudge steps
 * ONE, deliberately, because a nudge is what you use when you know exactly
 * where you are going. A shove sweeps, because a shove is what you use when you
 * are crossing thirty permanents to reach the lands. The thumb already knows
 * which one it is doing; the loop only has to read it.
 *
 * Two knobs, both linear and both honest:
 *
 *   push   how far past FIRE the stick is, rescaled to 0..1. Picks the interval
 *          between REPEAT_SLOW and REPEAT_FAST.
 *   run    how many repeats this hold has already fired. Eases the interval down
 *          a further 28% over the first seven, which is what stops a long lane
 *          feeling like a metronome you are waiting on.
 *
 * A d-pad and the keyboard have no analog to read, so they stand at `KEY_T` --
 * deliberately the middle of the range rather than either end, because a
 * digital press means "one step" and must not inherit the sweep.
 *
 * Every number lives in `RAMP` as one object. They are reasoned rather than
 * measured -- nobody has held a Deck against this build -- so the first person
 * who does can settle them here without reading the polling loop.
 * the handheld round records that as an explicitly open question.
 */

/** The ramp's tunables. One object, so a Deck can settle them in one place. */
export const RAMP = {
  /** ms before the first repeat, at a nudge. */
  firstSlow: 360,
  /** ...and at a full shove. */
  firstFast: 180,
  /** ms between repeats, at a nudge. */
  slow: 155,
  /** ...and at a full shove. */
  fast: 46,
  /** Never faster than this, however long the hold. */
  floor: 38,
  /** Where a digital direction (d-pad, keyboard) sits on the ramp. */
  keyT: 0.5,
  /** Repeats the run-in takes to reach `accelFloor`. */
  accelOver: 7,
  /** ...the multiple of the interval it eases down to. */
  accelFloor: 0.72,
} as const;

/**
 * Stick hysteresis.
 *
 * Without it a stick held toward a corner sits on the boundary of two sectors
 * and chatters between them. Over thirty permanents in ragged rows that reads
 * as "the cursor is broken", and the blame lands on the spatial nav rather than
 * on the polling loop.
 */
export const STICK = {
  /** Deck sticks rest noisily; past the noise. */
  dead: 0.3,
  /** A direction is meant once the stick crosses this. */
  fire: 0.55,
  /** ...and is not meant again until it drops below this. */
  release: 0.35,
} as const;

const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;

export const clamp01 = (n: number): number => (n < 0 ? 0 : n > 1 ? 1 : n);

/**
 * Where a stick magnitude sits on the ramp: 0 is a nudge, 1 is a full shove.
 *
 * Below `release` the stick is centred, so whatever is driving the direction is
 * digital and stands at `keyT`. Callers that already know the source is digital
 * should pass `null` rather than a magnitude.
 */
export function pushOf(magnitude: number | null): number {
  if (magnitude === null || magnitude < STICK.release) return RAMP.keyT;
  return clamp01((magnitude - STICK.fire) / (1 - STICK.fire));
}

/**
 * The interval before the next repeat of a held direction, in ms.
 *
 * `first` is the initial delay-before-autorepeat; afterwards the interval eases
 * down with `run`. Both ends are clamped: the ramp may never outrun `floor`.
 */
export function repeatMs(push: number, run: number, first: boolean): number {
  const t = clamp01(push);
  if (first) return lerp(RAMP.firstSlow, RAMP.firstFast, t);
  const accel = Math.max(
    RAMP.accelFloor,
    1 - (Math.max(0, run) / RAMP.accelOver) * (1 - RAMP.accelFloor),
  );
  return Math.max(RAMP.floor, lerp(RAMP.slow, RAMP.fast, t) * accel);
}

/**
 * Which of the four sectors a stick is in, with hysteresis applied.
 *
 * `latched` is the sector currently held, or null while centred. A new
 * direction only latches past `fire`, and nothing new latches until the stick
 * falls back inside `release` -- which is the whole point of the function.
 */
export type Dir = "up" | "down" | "left" | "right";

export function sector(x: number, y: number, latched: Dir | null): Dir | null {
  const m = Math.hypot(x, y);
  if (m < STICK.release) return null;
  if (latched && m < STICK.fire) return latched;
  if (m < STICK.fire) return null;
  return Math.abs(x) > Math.abs(y) ? (x < 0 ? "left" : "right") : y < 0 ? "up" : "down";
}

/** Deadzone and rescale a stick so it leaves 0 cleanly. */
export function deadzone(x: number, y: number): { x: number; y: number } {
  const m = Math.hypot(x, y);
  if (m < STICK.dead) return { x: 0, y: 0 };
  const k = (m - STICK.dead) / (1 - STICK.dead) / m;
  return { x: x * k, y: y * k };
}
