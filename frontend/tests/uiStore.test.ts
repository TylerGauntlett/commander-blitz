/**
 * Narration pacing.
 *
 * The multipliers are divisors on every beat's hold and every FX lifetime, so
 * their absolute values are the game's sense of speed. Cycle 3 halved them:
 * "the game moves too quickly" (docs/playtest-feedback-02.md) was true at both
 * watchable settings, and the slowest thing on offer was 1x.
 *
 * The per-beat holds in `logic/events.ts` were deliberately left alone -- they
 * encode the *relative* weight of events, and rescaling twenty of them by hand
 * to change one thing is how a palette drifts.
 */

import { describe, expect, it } from "vitest";
import { SPEED_MULTIPLIER, type Speed } from "../src/state/uiStore";

const WATCHABLE: Speed[] = ["cinematic", "fast"];

describe("SPEED_MULTIPLIER", () => {
  it("makes the default setting the old 'cinematic' pace", () => {
    // `fast` is the stored default, and it used to divide holds by 2.
    expect(SPEED_MULTIPLIER.fast).toBe(1);
  });

  it("offers something slower than the old floor", () => {
    // There was no way to ask for less than 1x, which is what the complaint was
    // really about.
    expect(SPEED_MULTIPLIER.cinematic).toBeLessThan(1);
  });

  it("orders the watchable settings slowest first", () => {
    expect(SPEED_MULTIPLIER.cinematic).toBeLessThan(SPEED_MULTIPLIER.fast);
  });

  it("keeps every watchable setting slow enough to read a beat", () => {
    // A 260ms land drop must not fall under the ~120ms it takes to notice one.
    for (const speed of WATCHABLE) {
      expect(260 / SPEED_MULTIPLIER[speed]).toBeGreaterThan(120);
    }
  });

  it("keeps instant effectively instant", () => {
    // Not a speed so much as a bypass: `narration.ts` short-circuits on it and
    // drops beats rather than holding them for ~0ms.
    expect(1100 / SPEED_MULTIPLIER.instant).toBeLessThan(5);
  });

  it("defines every speed exactly once", () => {
    expect(Object.keys(SPEED_MULTIPLIER).sort()).toEqual(["cinematic", "fast", "instant"]);
  });

  it("never divides by zero or a negative", () => {
    for (const value of Object.values(SPEED_MULTIPLIER)) {
      expect(value).toBeGreaterThan(0);
    }
  });
});
