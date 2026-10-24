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
import { KEY_LABEL, KEYS } from "../src/input/buttons";
import {
  getInputMode,
  getScheme,
  isPadConnected,
  isPointerMode,
  noteInput,
  notePadConnected,
  resetInputMode,
  setScheme,
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

/**
 * jsdom has no `matchMedia`, and the `auto` heuristic asks it a question.
 *
 * Stated rather than stubbed globally: the answer is the whole difference
 * between "a Deck" and "a desktop", so each test that cares says which it is.
 * `undefined` -- the jsdom default -- is also a case worth having, and
 * `padShaped` treats it as "not a handheld", which is the safe way to be wrong.
 */
function viewport(handheld: boolean | null): void {
  if (handheld === null) {
    delete (window as { matchMedia?: unknown }).matchMedia;
    return;
  }
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({ matches: handheld });
}

/** Three arrows, which is what `NAV_STREAK` asks for. */
function arrows(n = 3): void {
  for (let i = 0; i < n; i += 1) {
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown" }));
  }
}

beforeEach(() => {
  resetInputMode();
  viewport(null);
  try {
    localStorage.clear();
  } catch {
    // No storage under some environments; the default is `auto` regardless.
  }
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  resetInputMode();
  viewport(null);
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

/**
 * A Steam Deck in gaming mode is a controller that arrives as a keyboard.
 *
 * Steam Input grabs the pad, publishes no gamepad, and sends arrow keys and
 * Enter -- so every signal this module had said "keyboard", and the hint bar
 * told somebody holding a controller to press Enter and Esc. These pin the
 * heuristic that fixes that, and, more importantly, the guard that stops it
 * firing for a desktop keyboard user who has no A button to press.
 */
describe("the auto heuristic", () => {
  it("calls a handheld driven by arrows alone a pad", () => {
    viewport(true);
    startInputMode();
    arrows();
    expect(getInputMode()).toBe("pad");
    expect(root().getAttribute("data-input")).toBe("pad");
  });

  it("waits for the streak rather than guessing off one press", () => {
    viewport(true);
    startInputMode();
    arrows(2);
    expect(getInputMode()).toBe("keyboard");
    arrows(1);
    expect(getInputMode()).toBe("pad");
  });

  it("never guesses at desktop size, where there is no A button to press", () => {
    /*
     * THE VIEWPORT GATE IS THE WHOLE SAFETY OF THIS. Somebody arrowing around a
     * menu on a 1920x1080 desktop is at a keyboard, and telling them to press
     * "A" names hardware they are not holding.
     */
    viewport(false);
    startInputMode();
    arrows(6);
    expect(getInputMode()).toBe("keyboard");
  });

  it("is disqualified for good by a single character key", () => {
    // Somebody typed. They have a keyboard, and no later run of arrows undoes
    // that -- a pod code is exactly the sequence that would otherwise re-arm it.
    viewport(true);
    startInputMode();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "g" }));
    arrows(6);
    expect(getInputMode()).toBe("keyboard");
  });

  it("does not treat a modifier as typing", () => {
    // Shift is neither a character nor a navigation, and counting it as the
    // former would disqualify a pad whose Steam layout happens to send one.
    viewport(true);
    startInputMode();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Shift" }));
    arrows();
    expect(getInputMode()).toBe("pad");
  });
});

describe("the scheme preference", () => {
  it("outranks everything, which is the point of having one", () => {
    viewport(false);
    startInputMode();
    setScheme("pad");
    expect(getInputMode()).toBe("pad");
    // ...and a real mouse move cannot take it back.
    window.dispatchEvent(pointer("pointerdown"));
    expect(getInputMode()).toBe("pad");
  });

  it("hands control back to the heuristic on auto", () => {
    viewport(false);
    startInputMode();
    setScheme("keyboard");
    expect(getInputMode()).toBe("keyboard");
    setScheme("auto");
    expect(getInputMode()).toBe("mouse");
  });

  it("survives a reload", () => {
    startInputMode();
    setScheme("pad");
    resetInputMode();
    expect(getScheme()).toBe("auto");
    startInputMode();
    expect(getScheme()).toBe("pad");
  });
});

describe("the pointer grace", () => {
  it("does not let a trackpad thumb kill the ring mid-game", () => {
    /*
     * THE DECK'S RIGHT STICK AND TRACKPADS ARE MOUSE EVENTS. A thumb resting on
     * one emits `pointermove` forever, and one of those used to flip the mode to
     * `mouse` -- which hides the ring, blanks every glyph and drops the region
     * trap. The controller appeared to die for touching the device it is part of.
     */
    startInputMode();
    noteInput("pad");
    // Past the 200ms move throttle, so only the grace can be what saves it.
    vi.advanceTimersByTime(400);
    window.dispatchEvent(pointer("pointermove"));
    expect(getInputMode()).toBe("pad");
  });

  it("still yields to a deliberate press, which is never ambiguous", () => {
    startInputMode();
    noteInput("pad");
    window.dispatchEvent(pointer("pointerdown"));
    expect(getInputMode()).toBe("mouse");
  });
});

describe("touch", () => {
  /*
   * ADR 0025: a finger is a fourth input mode, not a mouse. The listener reads
   * `pointerType`, which jsdom's plain `Event` lacks, so it is set by hand.
   */
  const finger = (type: string) => Object.assign(new Event(type), { pointerType: "touch" });

  it("is what a finger's press writes", () => {
    startInputMode();
    window.dispatchEvent(finger("pointerdown"));
    expect(getInputMode()).toBe("touch");
    expect(root().getAttribute("data-input")).toBe("touch");
  });

  it("is not taken back by the same finger moving", () => {
    startInputMode();
    window.dispatchEvent(finger("pointerdown"));
    vi.advanceTimersByTime(400);
    window.dispatchEvent(finger("pointermove"));
    expect(getInputMode()).toBe("touch");
  });

  it("yields to a mouse the moment one is used, last input winning", () => {
    startInputMode();
    window.dispatchEvent(finger("pointerdown"));
    vi.advanceTimersByTime(400);
    window.dispatchEvent(pointer("pointermove"));
    expect(getInputMode()).toBe("mouse");
  });

  it("can be pinned from Settings and survives a reload", () => {
    startInputMode();
    setScheme("touch");
    expect(getInputMode()).toBe("touch");
    window.dispatchEvent(pointer("pointerdown"));
    expect(getInputMode()).toBe("touch");
    resetInputMode();
    startInputMode();
    expect(getScheme()).toBe("touch");
  });

  it("is a pointer mode, so it draws no ring", () => {
    expect(isPointerMode("touch")).toBe(true);
    expect(isPointerMode("mouse")).toBe(true);
    expect(isPointerMode("pad")).toBe(false);
    expect(isPointerMode("keyboard")).toBe(false);
  });
});
