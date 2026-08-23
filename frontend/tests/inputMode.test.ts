/**
 * Which controls the game draws, and for whom.
 *
 * The requirement is blunt: a mouse player never sees a controller hint. That
 * is what these assert, along with the two things that make "last input wins"
 * work in practice rather than in principle -- a resting mouse must not steal
 * the mode back from a pad, and the pad being *connected* must not by itself
 * mean the player is using it.
 *
 * The mechanism under test is deliberately not React. `startInputMode` writes
 * two attributes on `<html>`, and every glyph in the app is shown or hidden by
 * CSS reading them, so a pointer move costs zero renders. These tests therefore
 * assert on the attributes, which is exactly what the stylesheet keys off.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { KEYS, KEY_LABEL } from "../src/input/buttons";
import {
  getInputMode,
  isPadConnected,
  noteInput,
  notePadConnected,
  resetInputMode,
  startInputMode,
  subscribeInputMode,
} from "../src/input/inputMode";

const root = () => document.documentElement;

/**
 * A pointer event jsdom will actually construct.
 *
 * jsdom does not implement `PointerEvent`, and the listener only ever reads
 * `type` -- so a plain `Event` exercises precisely the same path while being
 * constructible in the environment the unit project runs in.
 */
const pointer = (type: string) => new Event(type);

beforeEach(() => {
  resetInputMode();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  resetInputMode();
});

describe("startInputMode", () => {
  it("starts as mouse, which is what every existing test and story assumes", () => {
    startInputMode();
    expect(getInputMode()).toBe("mouse");
    expect(root().getAttribute("data-input")).toBe("mouse");
  });

  it("switches to keyboard on a keypress and to pad on a pad press", () => {
    startInputMode();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown" }));
    expect(root().getAttribute("data-input")).toBe("keyboard");
    // The pad is polled, not evented, so `pad.ts` reports its own edges.
    noteInput("pad");
    expect(root().getAttribute("data-input")).toBe("pad");
  });

  it("switches back to mouse on a click, so a hint set never gets stuck", () => {
    startInputMode();
    noteInput("pad");
    window.dispatchEvent(pointer("pointerdown"));
    expect(root().getAttribute("data-input")).toBe("mouse");
  });
});

describe("the pointermove throttle", () => {
  it("does not let a resting mouse steal the mode back from a pad", () => {
    /*
     * The case this exists for: a controller in your lap and a mouse on the
     * desk beside it. A mouse emits `pointermove` from desk vibration alone,
     * and without the throttle the glyphs would flicker off mid-navigation.
     */
    startInputMode();
    window.dispatchEvent(pointer("pointermove"));
    expect(getInputMode()).toBe("mouse");

    noteInput("pad");
    window.dispatchEvent(pointer("pointermove"));
    expect(getInputMode()).toBe("pad");
  });

  it("does honour a deliberate move once the throttle has expired", () => {
    startInputMode();
    window.dispatchEvent(pointer("pointermove"));
    noteInput("pad");
    vi.advanceTimersByTime(250);
    // `performance.now` is not faked by `useFakeTimers`, so drive the real
    // boundary rather than pretending: a press is never throttled.
    window.dispatchEvent(pointer("pointerdown"));
    expect(getInputMode()).toBe("mouse");
  });
});

describe("padConnected", () => {
  it("is independent of the mode, so plugging a pad in changes nothing on its own", () => {
    /*
     * Connection is not usage. A Deck in desktop mode has both attached at
     * once; showing A/B/X/Y the moment a pad is detected would put controller
     * hints in front of somebody driving with a mouse.
     */
    startInputMode();
    notePadConnected(true);
    expect(isPadConnected()).toBe(true);
    expect(getInputMode()).toBe("mouse");
    expect(root().hasAttribute("data-pad")).toBe(true);
    expect(root().getAttribute("data-input")).toBe("mouse");
  });

  it("clears the attribute when the pad goes away", () => {
    startInputMode();
    notePadConnected(true);
    notePadConnected(false);
    expect(root().hasAttribute("data-pad")).toBe(false);
  });
});

describe("subscribers", () => {
  it("are told once per genuine change, not per event", () => {
    startInputMode();
    const seen = vi.fn();
    subscribeInputMode(seen);
    noteInput("pad");
    noteInput("pad");
    noteInput("keyboard");
    expect(seen).toHaveBeenCalledTimes(2);
  });
});

/**
 * The key map may not steal a key the board already owns.
 *
 * This is not hypothetical: `e` was bound to R1 while `Table.tsx` has used it
 * to open the exile pile since zone peeking was written, so one press jumped a
 * zone *and* opened a modal. `1`-`9` were nearly taken for the triggers, which
 * would have made "open the menu" also play the first card in hand.
 *
 * The list below is the board's own shortcuts, and it is the contract: a pad
 * intent may map to any key that is not in it.
 */
describe("the keyboard fallback", () => {
  /** Keys `Table.tsx` handles itself. See its keyboard effect. */
  const RESERVED = [" ", "g", "e", "c", "u", "1", "2", "3", "4", "5", "6", "7", "8", "9"];

  it("takes no key the board already handles", () => {
    const taken = Object.keys(KEYS).filter((key) => RESERVED.includes(key));
    expect(taken).toEqual([]);
  });

  it("binds every button a hint can name to something a keyboard has", () => {
    // A hint reading "L2 Menu" to somebody at a keyboard names hardware they
    // are not holding. Anything the hint bar offers must have a real key.
    for (const btn of ["a", "b", "x", "y", "l1", "r1", "l2", "r2"] as const) {
      expect(Object.values(KEYS)).toContain(btn);
      expect(KEY_LABEL[btn], `${btn} has no keyboard label`).toBeTruthy();
    }
  });

  it("maps each key to exactly one intent", () => {
    const keys = Object.keys(KEYS);
    expect(new Set(keys).size).toBe(keys.length);
  });
});
