/**
 * The `R2` board peek: each press reads the next opponent in seat order, and
 * letting go puts your own board back.
 */

import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

type Frame = { r2: number };
const frames = new Set<(frame: Frame) => void>();
vi.mock("../src/input/pad", () => ({
  onFrame: (handler: (frame: Frame) => void) => {
    frames.add(handler);
    return () => frames.delete(handler);
  },
}));

const { nextOpponent, useOpponentReading } = await import("../src/input/useOpponentReading");

function trigger(r2: number): void {
  act(() => {
    for (const handler of frames) handler({ r2 });
  });
}

beforeEach(() => frames.clear());

describe("nextOpponent", () => {
  it("starts at the first opponent and wraps", () => {
    expect(nextOpponent([1, 2, 3], null)).toBe(1);
    expect(nextOpponent([1, 2, 3], 1)).toBe(2);
    expect(nextOpponent([1, 2, 3], 3)).toBe(1);
  });

  it("starts over when the last seat read has left the game", () => {
    expect(nextOpponent([1, 3], 2)).toBe(1);
  });

  it("names nobody with nobody to read", () => {
    expect(nextOpponent([], null)).toBeNull();
  });
});

describe("useOpponentReading", () => {
  it("press, release, press walks the table", () => {
    const opponents = [1, 2];
    const { result } = renderHook(() => useOpponentReading(true, opponents));
    expect(result.current).toBeNull();

    trigger(1);
    expect(result.current).toBe(1);
    // Held: a frame later it is still the same seat, not the next one.
    trigger(1);
    expect(result.current).toBe(1);

    trigger(0);
    expect(result.current).toBeNull();

    trigger(1);
    expect(result.current).toBe(2);
    trigger(0);
    trigger(1);
    expect(result.current).toBe(1);
  });

  it("does nothing off the handheld layout", () => {
    const { result } = renderHook(() => useOpponentReading(false, [1, 2]));
    trigger(1);
    expect(result.current).toBeNull();
  });
});
