/**
 * Making the cards themselves move.
 *
 * Every effect on this board used to be drawn *over* the table: a numeral above
 * a creature, a ring around it, a ghost where it used to be. The permanents
 * never moved. That is the single reason combat did not read as combat -- an
 * attack was an arrow and a banner, and the two creatures involved sat
 * perfectly still through the whole exchange.
 *
 * An actuator is a handle on one live card that can push it around for a moment
 * and then put it back. `Card` registers one on mount, keyed by oid; a combat
 * choreography looks up the attacker and tells it to lunge.
 *
 * ## Two rules, both load-bearing
 *
 * **Nothing here may cause a React render.** A four-creature exchange drives
 * eight cards at once, sixty times a second, on a board that already holds
 * ninety of them. These write to Motion values directly -- the same channel
 * `whileHover` uses -- so the reconciler never hears about it.
 *
 * **Transforms are additive to a layer nobody else owns.** `Card` is already
 * two motion layers because they collided once: the outer one owns position
 * (`layoutId`, drag, hover lift) and the inner owns the 90-degree tap rotation,
 * and when both wrote `transform` a tapped creature untapped itself the moment
 * you picked it up. Actuators get a *third* layer between them, so a lunging
 * creature can still be tapped, still be mid-flight from a `layoutId` change,
 * and still be picked up, without any of the four fighting over one matrix.
 */

import type { MotionValue } from "motion/react";
import { prefersReducedMotion } from "./reducedMotion";
import { overTime } from "./scheduler";

export interface Point {
  x: number;
  y: number;
}

/**
 * The motion values one card hands over.
 *
 * Deliberately the raw values rather than an `AnimationControls`: the effects
 * below are physical curves -- an asymmetric lunge, a decaying shudder -- and
 * expressing those as spring keyframes means fighting the spring's own timing
 * for control the frame loop gives away for free.
 */
export interface CardChannel {
  x: MotionValue<number>;
  y: MotionValue<number>;
  rotate: MotionValue<number>;
  scale: MotionValue<number>;
}

export interface Actuator {
  /** Drive toward a board point, hold at the far end, snap back. */
  lunge(toward: Point, opts?: { reach?: number; ms?: number }): void;
  /** Get knocked away from a point. `power` is 0..1. */
  recoil(from: Point, power: number): void;
  /** Vibrate in place, decaying. `power` is 0..1. */
  shudder(power: number): void;
  /** A quick squash-and-swell, for something happening *to* the card. */
  pulse(power?: number): void;
  /** Cancel whatever is running and return to rest. */
  rest(): void;
}

const channels = new Map<number, CardChannel>();
/** Cancels for whatever each oid is currently doing, so effects do not stack. */
const running = new Map<number, () => void>();

/** How far a lunge travels, as a fraction of the distance to its target. */
const REACH = 0.42;
/** Ceiling in pixels: across a 4-player pod a full-fraction lunge would fly. */
const MAX_REACH = 92;

function stop(oid: number): void {
  running.get(oid)?.();
  running.delete(oid);
}

function begin(oid: number, cancel: () => void): void {
  stop(oid);
  running.set(oid, cancel);
}

function settle(channel: CardChannel): void {
  channel.x.set(0);
  channel.y.set(0);
  channel.rotate.set(0);
  channel.scale.set(1);
}

/**
 * The lunge curve.
 *
 * Not a sine and not a spring. A strike is asymmetric: it goes out fast, hangs
 * for an instant at the point of contact -- which is where the impact burst and
 * the damage numeral land -- and comes back slower than it left. A symmetric
 * ease has no moment of contact in it at all, which is what makes a symmetric
 * lunge look like a card wobbling rather than a creature hitting something.
 */
function strikeCurve(t: number): number {
  if (t < 0.32) {
    const out = t / 0.32;
    return out * out * (3 - 2 * out); // smoothstep out
  }
  if (t < 0.46) return 1; // contact
  const back = (t - 0.46) / 0.54;
  return 1 - back * back * (3 - 2 * back);
}

function makeActuator(oid: number, channel: CardChannel): Actuator {
  const reduced = () => prefersReducedMotion();

  return {
    lunge(toward, opts = {}) {
      if (reduced()) return;
      const el = document.querySelector(`[data-oid="${oid}"]`);
      if (!el) return;
      const box = el.getBoundingClientRect();
      // The card's own centre in viewport space. `toward` is board-relative,
      // so the board's origin has to come back out of it -- the same
      // conversion `FxLayer` does in reverse when it places an anchor.
      const board = el.closest<HTMLElement>("[data-fx-origin]");
      const origin = board?.getBoundingClientRect();
      const targetX = toward.x + (origin?.left ?? 0);
      const targetY = toward.y + (origin?.top ?? 0);
      const dx = targetX - (box.left + box.width / 2);
      const dy = targetY - (box.top + box.height / 2);
      const distance = Math.hypot(dx, dy) || 1;
      const reach = Math.min(opts.reach ?? MAX_REACH, distance * REACH);
      const nx = (dx / distance) * reach;
      const ny = (dy / distance) * reach;
      // Lean into the direction of travel. A card that translates without
      // rotating reads as a sliding token; the tilt is what makes it a swing.
      const tilt = Math.max(-14, Math.min(14, (dx / distance) * 14));

      const cancel = overTime(opts.ms ?? 340, (t) => {
        const k = strikeCurve(t);
        channel.x.set(nx * k);
        channel.y.set(ny * k);
        channel.rotate.set(tilt * k);
        channel.scale.set(1 + 0.06 * k);
        if (t >= 1) settle(channel);
      });
      begin(oid, () => {
        cancel();
        settle(channel);
      });
    },

    recoil(from, power) {
      if (reduced()) return;
      const el = document.querySelector(`[data-oid="${oid}"]`);
      if (!el) return;
      const box = el.getBoundingClientRect();
      const board = el.closest<HTMLElement>("[data-fx-origin]");
      const origin = board?.getBoundingClientRect();
      const dx = box.left + box.width / 2 - (from.x + (origin?.left ?? 0));
      const dy = box.top + box.height / 2 - (from.y + (origin?.top ?? 0));
      const distance = Math.hypot(dx, dy) || 1;
      const kick = 10 + 26 * Math.min(1, power);
      const nx = (dx / distance) * kick;
      const ny = (dy / distance) * kick;

      const cancel = overTime(300, (t) => {
        // Knocked back immediately, then eased home: the opposite asymmetry to
        // a lunge, because the card is not choosing to do this.
        const k = t < 0.18 ? t / 0.18 : 1 - (t - 0.18) / 0.82;
        channel.x.set(nx * k);
        channel.y.set(ny * k);
        channel.rotate.set(-8 * Math.min(1, power) * k);
        if (t >= 1) settle(channel);
      });
      begin(oid, () => {
        cancel();
        settle(channel);
      });
    },

    shudder(power) {
      if (reduced()) return;
      const amp = 7 * Math.min(1, power);
      const cancel = overTime(260, (t) => {
        const decay = 1 - t;
        // 34 rad over the life is ~5 full oscillations: fast enough to read as
        // a vibration rather than as the card being dragged side to side.
        const wave = Math.sin(t * 34);
        channel.x.set(wave * amp * decay);
        channel.rotate.set(wave * 3 * decay);
        if (t >= 1) settle(channel);
      });
      begin(oid, () => {
        cancel();
        settle(channel);
      });
    },

    pulse(power = 1) {
      if (reduced()) return;
      const swell = 0.12 * Math.min(1, power);
      const cancel = overTime(280, (t) => {
        channel.scale.set(1 + Math.sin(t * Math.PI) * swell);
        if (t >= 1) settle(channel);
      });
      begin(oid, () => {
        cancel();
        settle(channel);
      });
    },

    rest() {
      stop(oid);
      settle(channel);
    },
  };
}

/** Called by `Card` on mount. Returns the release for its cleanup. */
export function register(oid: number, channel: CardChannel): () => void {
  channels.set(oid, channel);
  return () => {
    stop(oid);
    if (channels.get(oid) === channel) channels.delete(oid);
  };
}

/**
 * The actuator for a card, or null if it is not on screen.
 *
 * Null is the normal case rather than an error: choreography is built from an
 * event log that may name a creature which has already died, or one belonging
 * to a zone this seat cannot see. Callers skip it and animate the rest.
 */
export function drive(oid: number): Actuator | null {
  const channel = channels.get(oid);
  return channel ? makeActuator(oid, channel) : null;
}

/** Stop everything and return every card to rest. Skip, and teardown. */
export function restAll(): void {
  for (const oid of [...running.keys()]) stop(oid);
  for (const channel of channels.values()) settle(channel);
}
