/**
 * A screen leaving, on a clock.
 *
 * The app swaps screens under `AnimatePresence mode="wait"`, which mounts the
 * next screen only once the current one has reported its exit complete. An exit
 * animation that never completes is therefore a blank app, so `Screen` reports
 * itself removable on a timer rather than on the animation. jsdom can see the
 * hand-off, because it is a timer and not a layout.
 */

import { act, cleanup, render, screen } from "@testing-library/react";
import { AnimatePresence } from "motion/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Screen } from "../src/components/screen/Screen";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const app = (which: "door" | "table") => (
  <AnimatePresence mode="wait">
    {which === "door" ? (
      <Screen key="door" testId="door">
        <p>door</p>
      </Screen>
    ) : (
      <Screen key="table" variant="zoom" testId="table">
        <p>table</p>
      </Screen>
    )}
  </AnimatePresence>
);

describe("Screen", () => {
  it("marks itself closing at once, and hands over to the next screen on the clock", () => {
    vi.useFakeTimers();
    const { rerender } = render(app("door"));
    expect(screen.getByTestId("door").hasAttribute("data-closing")).toBe(false);

    rerender(app("table"));
    // Leaving: still mounted for its fade, marked so nothing lands on it, and
    // the next screen waits its turn.
    expect(screen.getByTestId("door").hasAttribute("data-closing")).toBe(true);
    expect(screen.queryByTestId("table")).toBeNull();

    act(() => vi.advanceTimersByTime(100));
    expect(screen.queryByTestId("door")).not.toBeNull();

    // On the clock, whatever any animation had to say about it.
    act(() => vi.advanceTimersByTime(400));
    expect(screen.queryByTestId("door")).toBeNull();
    expect(screen.queryByTestId("table")).not.toBeNull();
  });
});
