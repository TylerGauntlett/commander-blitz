/**
 * The opening hand leaving, on a clock.
 *
 * The stories cover the stage standing still; what jsdom can add is the
 * departure, because it is a timer and not a layout. `OpeningHand.tsx` says
 * why the stage leaves on a timer: `AnimatePresence` removes a child only once
 * every exit inside it has reported complete, and one that never did left an
 * invisible stage over the board.
 */

import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OpeningHand } from "../src/components/game/OpeningHand";
import { action, card, gameView, pending, player } from "./fixtures";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const noop = () => undefined;

const seven = Array.from({ length: 7 }, (_, i) =>
  card({ oid: 80 + i, name: `Card ${i}`, zone: "hand", controller: 0, owner: 0 }),
);

const asked = gameView({
  players: [player({ hand: seven }), player({ pid: 1, name: "AI 1", hand: null })],
  pending: pending({ kind: "mulligan", prompt: "Keep this hand?" }),
});

const keepOrMull = [
  action({ id: "a0-mulligan", kind: "mulligan", label: "Mulligan" }),
  action({ id: "a1-keep", kind: "keep", label: "Keep" }),
];

describe("OpeningHand leaving", () => {
  it("marks itself closing at once, and is gone once the clock runs out", () => {
    vi.useFakeTimers();
    const { rerender } = render(
      <OpeningHand state={asked} actions={keepOrMull} onAct={noop} disabled={false} />,
    );
    const stage = screen.getByTestId("opening-hand");
    expect(stage.hasAttribute("data-closing")).toBe(false);

    // The answer landed: the decision has moved on and there is nothing to press.
    const answered = gameView({ ...asked, pending: pending({ kind: "priority", player: 1 }) });
    rerender(<OpeningHand state={answered} actions={[]} onAct={noop} disabled={false} />);
    expect(screen.getByTestId("opening-hand").hasAttribute("data-closing")).toBe(true);

    // Not gone yet: the fade is still being shown.
    act(() => vi.advanceTimersByTime(100));
    expect(screen.queryByTestId("opening-hand")).not.toBeNull();

    // And gone on the clock, whatever any animation had to say about it.
    act(() => vi.advanceTimersByTime(400));
    expect(screen.queryByTestId("opening-hand")).toBeNull();
  });
});
