/**
 * The ring's spring.
 *
 * The reason this is a closed form rather than `v += (k*dx - d*v) * dt` is
 * entirely about two properties, and both are asserted here rather than
 * described in a comment: it is EXACT at any `dt`, so the ring behaves the same
 * on a 144Hz monitor and the Deck's 60Hz panel, and it stays stable when a
 * throttled or backgrounded tab hands it a whole second.
 *
 * The timing claims in `ring.ts` are load-bearing too -- "142ms settling, 2%
 * overshoot, within 2px in 117ms on a 200px hop" is what makes the ring not
 * slower than the CSS transition it replaces -- so they are checked, not
 * trusted.
 */

import { describe, expect, it } from "vitest";
import { LONG_HOP, longHop, type RingBox, SPRING, springStep } from "../src/input/ring";

const { w, z } = SPRING.full;

/**
 * `longHop` shortened to a start box, insisting there was one.
 *
 * The `null` return is a real answer -- "this hop is already short enough" --
 * and each test below has already decided which case it is exercising, so
 * asserting it here keeps the assertion at the top of the test rather than
 * burying a non-null claim inside the arithmetic.
 */
function shortened(from: RingBox, to: RingBox): RingBox {
  const start = longHop(from, to);
  expect(start).not.toBeNull();
  return start as RingBox;
}

/** When the spring FIRST comes within `px` of its target, in ms. */
function arrivesWithin(x0: number, px: number, limit = 600): number {
  let state = { x: x0, v: 0 };
  for (let t = 1; t <= limit; t += 1) {
    state = springStep(state.x, state.v, 0, w, z, 0.001);
    if (Math.abs(state.x) < px) return t;
  }
  return Number.POSITIVE_INFINITY;
}

/** Integrate from `x0` to 0 for `ms`, in steps of `stepMs`. */
function run(x0: number, ms: number, stepMs: number) {
  let state = { x: x0, v: 0 };
  const dt = stepMs / 1000;
  for (let t = 0; t < ms; t += stepMs) {
    state = springStep(state.x, state.v, 0, w, z, dt);
  }
  return state;
}

describe("springStep", () => {
  it("is frame-rate independent: one 16ms step equals four 4ms steps", () => {
    const coarse = springStep(200, 0, 0, w, z, 0.016);
    let fine = { x: 200, v: 0 };
    for (let i = 0; i < 4; i += 1) fine = springStep(fine.x, fine.v, 0, w, z, 0.004);
    expect(fine.x).toBeCloseTo(coarse.x, 9);
    expect(fine.v).toBeCloseTo(coarse.v, 9);
  });

  it("resolves a dropped second to 'the ring is where the cursor is'", () => {
    // The naive integrator launches across the screen here. The decay term goes
    // to zero on its own, so a huge dt is the correct picture rather than a bug.
    const after = springStep(1000, 0, 0, w, z, 1);
    expect(Math.abs(after.x)).toBeLessThan(0.001);
    expect(Math.abs(after.v)).toBeLessThan(0.001);
    expect(Number.isFinite(after.x)).toBe(true);
  });

  it("never diverges, however absurd the timestep", () => {
    for (const dt of [0.5, 2, 10, 120]) {
      const after = springStep(500, 4000, 0, w, z, dt);
      expect(Number.isFinite(after.x)).toBe(true);
      expect(Math.abs(after.x)).toBeLessThanOrEqual(500);
    }
  });

  it("settles in about 142ms, which is 4/(z*w)", () => {
    const settle = (4 / (z * w)) * 1000;
    expect(settle).toBeGreaterThan(130);
    expect(settle).toBeLessThan(155);
    // And it is genuinely at rest by then, not merely predicted to be.
    const done = run(200, settle, 4);
    expect(Math.abs(done.x)).toBeLessThan(200 * 0.02);
  });

  it("overshoots about 2% -- enough to read as landing, not as stopping", () => {
    const overshoot = Math.exp((-Math.PI * z) / Math.sqrt(1 - z * z));
    expect(overshoot).toBeGreaterThan(0.01);
    expect(overshoot).toBeLessThan(0.035);
  });

  it("first reaches 2px of a 200px hop by ~117ms, the moment the eye calls it arrived", () => {
    /*
     * FIRST arrival, not the value at a fixed instant. The 2px window is not
     * monotone and must not be asserted as though it were: the ring reaches it
     * around 105ms, then the deliberate 2% overshoot carries it back out to
     * ~4px before it settles. Sampling at one timestamp measures whichever side
     * of that bounce you happened to land on -- which is exactly the mistake
     * this comment exists to stop somebody making again.
     */
    expect(arrivesWithin(200, 2)).toBeLessThanOrEqual(117);
    // ...and not so early the travel is invisible, which would mean the spring
    // is doing nothing for the player it was added for.
    expect(arrivesWithin(200, 2)).toBeGreaterThan(60);
  });

  it("holds the arrival time roughly constant across distances", () => {
    /*
     * This is the property `longHop` exists to work around: a spring settles in
     * the same time however far it has to go, so a 1000px zone jump would fly
     * at ~13,000 px/s and strobe. Asserting it here is what makes the argument
     * in `longHop`'s header checkable rather than merely stated.
     */
    const near = arrivesWithin(100, 2);
    const far = arrivesWithin(800, 2);
    expect(Math.abs(far - near)).toBeLessThan(25);
  });

  it("keeps the overshoot small enough to read as landing", () => {
    let state = { x: 200, v: 0 };
    let worst = 0;
    for (let t = 0; t < 400; t += 1) {
      state = springStep(state.x, state.v, 0, w, z, 0.001);
      // Past the target, i.e. the far side of zero.
      if (state.x < 0) worst = Math.max(worst, -state.x);
    }
    expect(worst).toBeGreaterThan(0);
    expect(worst).toBeLessThan(200 * 0.035);
  });

  it("swift is quicker than full at the same distance", () => {
    const s = SPRING.swift;
    let state = { x: 200, v: 0 };
    for (let t = 0; t < 90; t += 1) state = springStep(state.x, state.v, 0, s.w, s.z, 0.001);
    expect(Math.abs(state.x)).toBeLessThan(Math.abs(run(200, 90, 1).x));
  });
});

describe("longHop", () => {
  const from = { x: 0, y: 0, w: 100, h: 140 };

  it("leaves a short hop alone, so ordinary travel is unchanged", () => {
    expect(longHop(from, { x: 200, y: 0, w: 100, h: 140 })).toBeNull();
  });

  it("starts a long hop exactly LONG_HOP out along its own approach line", () => {
    const to = { x: 1000, y: 0, w: 100, h: 140 };
    const start = shortened(from, to);
    expect(Math.hypot(to.x - start.x, to.y - start.y)).toBeCloseTo(LONG_HOP, 6);
  });

  it("keeps the direction, so the ring still enters from the correct side", () => {
    const to = { x: -1000, y: 500, w: 100, h: 140 };
    const start = shortened(from, to);
    // Same bearing from the destination back toward where it came from.
    const wanted = Math.atan2(from.y - to.y, from.x - to.x);
    const got = Math.atan2(start.y - to.y, start.x - to.x);
    expect(got).toBeCloseTo(wanted, 6);
  });

  it("interpolates the size, so the ring is not the wrong shape for the whole hop", () => {
    const to = { x: 1000, y: 0, w: 300, h: 60 };
    const start = shortened(from, to);
    // Partway between the two, on the same fraction as the position.
    const k = LONG_HOP / 1000;
    expect(start.w).toBeCloseTo(to.w - (to.w - from.w) * k, 6);
    expect(start.h).toBeCloseTo(to.h - (to.h - from.h) * k, 6);
  });

  it("does not divide by zero when the ring is already there", () => {
    expect(longHop(from, { ...from })).toBeNull();
  });
});
