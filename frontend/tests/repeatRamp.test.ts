/**
 * The analog repeat ramp, and the stick hysteresis under it.
 *
 * These are the numbers the design round could not settle, because nobody has
 * held a Deck against this build. So these tests deliberately pin the SHAPE of
 * the ramp -- monotone in push, monotone in run, floored, digital presses in
 * the middle -- rather than the constants themselves. Retuning `RAMP` on real
 * hardware is meant to be easy; breaking "a shove sweeps faster than a nudge"
 * is meant to be impossible.
 */

import { describe, expect, it } from "vitest";
import { type Dir, deadzone, pushOf, RAMP, repeatMs, STICK, sector } from "../src/input/repeat";

describe("pushOf", () => {
  it("puts a digital direction in the middle of the ramp, not at either end", () => {
    // A d-pad press and a key press mean "one step" and must not inherit the
    // sweep -- nor be punished with the slowest rate on the ramp.
    expect(pushOf(null)).toBe(RAMP.keyT);
    expect(RAMP.keyT).toBeGreaterThan(0);
    expect(RAMP.keyT).toBeLessThan(1);
  });

  it("treats a centred stick as digital", () => {
    // With a pad plugged in and the keyboard driving, the stick sits at rest.
    // Reading its magnitude would hand every key press the slowest rate.
    expect(pushOf(0)).toBe(RAMP.keyT);
    expect(pushOf(STICK.release - 0.01)).toBe(RAMP.keyT);
  });

  it("rises from 0 at the fire line to 1 at full deflection", () => {
    expect(pushOf(STICK.fire)).toBeCloseTo(0, 6);
    expect(pushOf(1)).toBeCloseTo(1, 6);
    expect(pushOf(0.8)).toBeGreaterThan(pushOf(0.6));
  });

  it("clamps past full deflection, since a stick can read slightly over 1", () => {
    expect(pushOf(1.4)).toBe(1);
  });
});

describe("repeatMs", () => {
  it("waits longer before the first repeat than between later ones", () => {
    expect(repeatMs(0.5, 0, true)).toBeGreaterThan(repeatMs(0.5, 0, false));
  });

  it("is monotone in push: a shove always sweeps faster than a nudge", () => {
    for (const first of [true, false]) {
      let last = Number.POSITIVE_INFINITY;
      for (const push of [0, 0.25, 0.5, 0.75, 1]) {
        const ms = repeatMs(push, 0, first);
        expect(ms).toBeLessThanOrEqual(last);
        last = ms;
      }
    }
  });

  it("is monotone in run: a long hold accelerates rather than metronoming", () => {
    let last = Number.POSITIVE_INFINITY;
    for (const run of [0, 1, 3, 7, 20]) {
      const ms = repeatMs(0.5, run, false);
      expect(ms).toBeLessThanOrEqual(last);
      last = ms;
    }
  });

  it("eases in over the first seven repeats and then stops easing", () => {
    const settled = repeatMs(0.5, RAMP.accelOver, false);
    expect(repeatMs(0.5, 100, false)).toBeCloseTo(settled, 6);
  });

  it("never outruns the floor, however hard or long the hold", () => {
    expect(repeatMs(1, 1000, false)).toBeGreaterThanOrEqual(RAMP.floor);
    expect(repeatMs(1, 1000, false)).toBeCloseTo(RAMP.floor, 6);
  });

  it("does not let a negative run speed things up", () => {
    expect(repeatMs(0.5, -5, false)).toBeCloseTo(repeatMs(0.5, 0, false), 6);
  });
});

describe("sector", () => {
  it("latches nothing until the stick crosses the fire line", () => {
    expect(sector(0.4, 0, null)).toBeNull();
    expect(sector(0.6, 0, null)).toBe("right");
  });

  it("holds its latch through the hysteresis band", () => {
    /*
     * The point of the whole function. A stick held toward a corner sits on the
     * boundary of two sectors; without this it chatters between them, and over
     * thirty permanents that reads as "the cursor is broken" -- with the blame
     * landing on the spatial nav rather than on the polling loop.
     */
    const held: Dir = "right";
    expect(sector(0.45, 0.05, held)).toBe("right");
    expect(sector(0.45, 0.05, null)).toBeNull();
  });

  it("releases only once the stick falls back inside the release band", () => {
    expect(sector(0.3, 0, "right")).toBeNull();
    expect(sector(STICK.release + 0.01, 0, "right")).toBe("right");
  });

  it("picks the dominant axis, so a diagonal resolves rather than doing both", () => {
    expect(sector(0.7, 0.5, null)).toBe("right");
    expect(sector(0.5, 0.7, null)).toBe("down");
    expect(sector(-0.7, -0.5, null)).toBe("left");
    expect(sector(-0.5, -0.7, null)).toBe("up");
  });
});

describe("deadzone", () => {
  it("reports exactly zero at rest, since Deck sticks rest noisily", () => {
    expect(deadzone(0.2, 0.1)).toEqual({ x: 0, y: 0 });
  });

  it("rescales so the stick leaves zero cleanly rather than jumping", () => {
    const justOut = deadzone(STICK.dead + 0.001, 0);
    expect(justOut.x).toBeGreaterThan(0);
    expect(justOut.x).toBeLessThan(0.01);
  });

  it("still reaches full deflection at the rim", () => {
    expect(deadzone(1, 0).x).toBeCloseTo(1, 6);
  });
});
