/**
 * `Y` -- and `i`, which `input/buttons.ts` maps to it -- reads the card in the
 * rail, full screen.
 *
 * It used to read `parseStop(getCursor())` and nothing else, which cost two
 * inputs their way in. A desktop player has no visible ring, so `i` over a
 * hovered card read wherever the invisible cursor last rested. And a panel row
 * or a seat names its card through `data-preview-oid`, not through its stop id,
 * so `Y` there was a `deny` (TECH_DEBT FB-08). Both now go through
 * `cursor.ts:readingOid`, which is the card the rail is showing.
 *
 * `pad.ts` is stubbed down to its registry: the binding is what is under test,
 * and a real pad loop is `pad.test.ts`'s business.
 */

import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { GameView } from "../src/api/types";
import { resetCursor, setCursor } from "../src/input/cursor";
import { noteInput, resetInputMode } from "../src/input/inputMode";
import { usePadBindings } from "../src/input/useTableInput";
import { useUiStore } from "../src/state/uiStore";
import * as scenarios from "../src/testing/scenarios";

const bound = vi.hoisted(() => new Map<string, () => void>());

vi.mock("../src/input/pad", async (importOriginal) => {
  const real = await importOriginal<typeof import("../src/input/pad")>();
  return {
    ...real,
    on: (button: string, handler: () => void) => {
      bound.set(button, handler);
      return () => bound.delete(button);
    },
    onAny: () => () => undefined,
  };
});

const noop = () => undefined;

function bind(state: GameView) {
  const setHeldCard = vi.fn();
  const cue = vi.fn();
  renderHook(() =>
    usePadBindings({
      back: noop,
      secondary: noop,
      stepGroup: noop,
      jumpToCommit: noop,
      toggleLogOverlay: noop,
      narration: { busy: false } as never,
      skipAll: noop,
      heldCard: null,
      setHeldCard,
      cue,
      state,
    }),
  );
  const press = () => {
    const y = bound.get("y");
    if (!y) throw new Error("nothing bound to y");
    y();
  };
  return { setHeldCard, cue, press };
}

beforeEach(() => {
  resetCursor();
  document.body.innerHTML = "";
});

afterEach(() => {
  cleanup();
  bound.clear();
  resetCursor();
  resetInputMode();
  document.body.innerHTML = "";
  useUiStore.setState({ hoveredOid: null });
});

describe("Y reads the card in the rail", () => {
  it("reads the card under the pointer, not the invisible ring's", () => {
    // The desktop case. The ring rests on Sol Ring where nobody can see it;
    // the pointer has put Llanowar Elves in the rail and `i` is pressed.
    const { state } = scenarios.earlyBoard();
    document.body.innerHTML = `<div class="table"><div data-stop="card:206"></div></div>`;
    setCursor("card:206");
    noteInput("mouse");
    useUiStore.setState({ hoveredOid: 205 });

    const { setHeldCard, press } = bind(state);
    press();
    expect(setHeldCard).toHaveBeenCalledWith(205);
  });

  it("reads what a panel row declares, where it used to deny", () => {
    // `hoverFor` has already written the row's `data-preview-oid` into the
    // rail; that is the card the press is about.
    const { state } = scenarios.earlyBoard();
    noteInput("pad");
    useUiStore.setState({ hoveredOid: 210 });

    const { setHeldCard, cue, press } = bind(state);
    press();
    expect(setHeldCard).toHaveBeenCalledWith(210);
    expect(cue).not.toHaveBeenCalled();
  });

  it("falls back to the ring's card when the rail is empty", () => {
    const { state } = scenarios.earlyBoard();
    document.body.innerHTML = `<div class="table"><div data-stop="card:206"></div></div>`;
    setCursor("card:206");

    const { setHeldCard, press } = bind(state);
    press();
    expect(setHeldCard).toHaveBeenCalledWith(206);
  });

  it("ignores a rail naming a card that is no longer anywhere", () => {
    // `hoveredOid` is only cleared by a leave handler; a card that left every
    // visible zone must not open an empty hold.
    const { state } = scenarios.earlyBoard();
    useUiStore.setState({ hoveredOid: 9999 });

    const { setHeldCard, cue, press } = bind(state);
    press();
    expect(setHeldCard).not.toHaveBeenCalled();
    expect(cue).toHaveBeenCalledWith("deny");
  });
});
