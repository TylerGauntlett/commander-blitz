/**
 * Pile arithmetic.
 *
 * Trivial to write and easy to get subtly wrong -- the cap and the ceiling are
 * the two things a reimplementation fumbles, and the symptom is a pile that
 * grows past its mat or a one-card graveyard that renders as nothing.
 */

import { describe, expect, it } from "vitest";
import { CARDS_PER_LEAF, MAX_LEAVES, pileLeaves } from "../src/logic/zones";

describe("pileLeaves", () => {
  it("draws nothing for an empty zone", () => {
    // The top leaf still renders, faded -- but no body leaves under it.
    expect(pileLeaves(0)).toBe(0);
  });

  it("draws a leaf for a single card", () => {
    // Ceiling, not floor: one card is a pile, not an empty space.
    expect(pileLeaves(1)).toBe(1);
  });

  it.each([
    [9, 1],
    [10, 2],
    [18, 2],
    [19, 3],
    [72, 8],
    [73, 9],
  ])("draws %i cards as %i leaves", (count, leaves) => {
    expect(pileLeaves(count)).toBe(leaves);
  });

  it("stops growing at the cap", () => {
    // Past this the stack is taller than the mat, and the extra height says
    // nothing a reader can use. The exact number is on the top leaf regardless.
    expect(pileLeaves(81)).toBe(MAX_LEAVES);
    expect(pileLeaves(200)).toBe(MAX_LEAVES);
    expect(pileLeaves(9999)).toBe(MAX_LEAVES);
  });

  it("never returns a fractional or negative count", () => {
    for (let n = -5; n < 120; n += 1) {
      const leaves = pileLeaves(n);
      expect(Number.isInteger(leaves)).toBe(true);
      expect(leaves).toBeGreaterThanOrEqual(0);
      expect(leaves).toBeLessThanOrEqual(MAX_LEAVES);
    }
  });

  it("grows monotonically", () => {
    // A pile that shrank as its zone grew would be worse than no pile at all.
    let previous = 0;
    for (let n = 0; n < 200; n += 1) {
      const leaves = pileLeaves(n);
      expect(leaves).toBeGreaterThanOrEqual(previous);
      previous = leaves;
    }
  });

  it("saturates exactly at the documented size", () => {
    expect(pileLeaves(MAX_LEAVES * CARDS_PER_LEAF)).toBe(MAX_LEAVES);
    expect(pileLeaves(MAX_LEAVES * CARDS_PER_LEAF - 1)).toBe(MAX_LEAVES);
    expect(pileLeaves((MAX_LEAVES - 1) * CARDS_PER_LEAF)).toBe(MAX_LEAVES - 1);
  });
});
