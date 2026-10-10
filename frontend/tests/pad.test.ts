/**
 * The polling loop, against pads that behave like real ones.
 *
 * This file exists because the controller work was reviewed and play-tested
 * entirely through the KEYBOARD FALLBACK -- the handheld playtest log says so
 * outright, and for good reason: Playwright cannot synthesise a `Gamepad`. That
 * exercises the ring, the trap and the ramp, and it exercises none of the code
 * that turns a real controller into those presses. Everything below that path
 * was therefore shipped unrun.
 *
 * So the pads here are modelled on what browsers actually hand over rather than
 * on what the spec promises: a sparse `getGamepads()`, a pad that only appears
 * after its first gesture, more than one device present at once, and a pad the
 * browser will not vouch for.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getInputMode, resetInputMode } from "../src/input/inputMode";
import { on, padDiagnostics, resetPad, startPad } from "../src/input/pad";

type Slot = Gamepad | null;

let slots: Slot[] = [];

function pad(over: Omit<Partial<Gamepad>, "buttons"> & { buttons?: number } = {}): Gamepad {
  const { buttons = 17, ...rest } = over;
  return {
    id: "Xbox Wireless Controller (STANDARD GAMEPAD Vendor: 045e Product: 0b13)",
    index: 0,
    connected: true,
    mapping: "standard",
    timestamp: 0,
    axes: [0, 0, 0, 0],
    ...rest,
    buttons: Array.from({ length: buttons }, () => ({
      pressed: false,
      touched: false,
      value: 0,
    })),
  } as unknown as Gamepad;
}

function press(target: Gamepad, index: number, down = true): void {
  (target.buttons as unknown as GamepadButton[])[index] = {
    pressed: down,
    touched: down,
    value: down ? 1 : 0,
  } as GamepadButton;
}

function axis(target: Gamepad, index: number, value: number): void {
  (target.axes as unknown as number[])[index] = value;
}

/** rAF driven by the fake clock, so a test can step frames deterministically. */
beforeEach(() => {
  vi.useFakeTimers();
  slots = [null, null, null, null];
  (navigator as unknown as { getGamepads: () => Slot[] }).getGamepads = () => slots;
  (globalThis as unknown as Record<string, unknown>).requestAnimationFrame = (
    cb: FrameRequestCallback,
  ) => setTimeout(() => cb(performance.now()), 16) as unknown as number;
  (globalThis as unknown as Record<string, unknown>).cancelAnimationFrame = (h: number) =>
    clearTimeout(h as unknown as ReturnType<typeof setTimeout>);
});

afterEach(() => {
  resetPad();
  resetInputMode();
  vi.useRealTimers();
});

describe("finding the pad at all", () => {
  /**
   * The sequence every real session has, and the one the old self-terminating
   * loop could not survive: no pad at page load, because no browser exposes one
   * until it has seen a button pressed.
   */
  it("sees a pad that only appears after start", () => {
    const hits: string[] = [];
    startPad();
    on("a", () => hits.push("a"));
    vi.advanceTimersByTime(500);
    expect(padDiagnostics().connected).toBe(false);
    expect(padDiagnostics().polling).toBe(true);

    const xbox = pad();
    slots = [xbox, null, null, null];
    vi.advanceTimersByTime(300);
    expect(padDiagnostics().connected).toBe(true);

    press(xbox, 0);
    vi.advanceTimersByTime(200);
    expect(hits).toEqual(["a"]);
  });

  /**
   * A pad in a slot that is not zero.
   *
   * `getGamepads()` is indexed by slot, and a controller that reconnects -- or
   * one plugged in behind another device -- comes back at a higher index.
   */
  it("reads a pad that is not in slot zero", () => {
    const hits: string[] = [];
    startPad();
    on("b", () => hits.push("b"));
    const xbox = pad({ index: 2 });
    slots = [null, null, xbox, null];
    vi.advanceTimersByTime(300);
    press(xbox, 1);
    vi.advanceTimersByTime(200);
    expect(hits).toEqual(["b"]);
  });

  /**
   * Two devices at once, which is the ordinary case on a Windows desktop:
   * Steam publishes a virtual pad beside the physical one.
   *
   * The idle device must not shadow the one being held. Reading only the first
   * entry meant every button came back neutral and the controller did nothing,
   * which is the exact symptom "the controller does not work at all" describes.
   */
  it("reads whichever of several pads is actually being used", () => {
    const hits: string[] = [];
    startPad();
    on("a", () => hits.push("a"));
    const idle = pad({ id: "Virtual pad", index: 0 });
    const held = pad({ index: 1 });
    slots = [idle, held, null, null];
    vi.advanceTimersByTime(300);
    press(held, 0);
    vi.advanceTimersByTime(200);
    expect(hits).toEqual(["a"]);
  });

  it("takes the stick of the pad pushed hardest, not the first one", () => {
    const hits: string[] = [];
    startPad();
    on("right", () => hits.push("right"));
    const idle = pad({ id: "Virtual pad", index: 0 });
    const held = pad({ index: 1 });
    slots = [idle, held, null, null];
    vi.advanceTimersByTime(300);
    axis(held, 0, 1);
    vi.advanceTimersByTime(100);
    expect(hits.length).toBeGreaterThan(0);
  });

  it("ignores a slot the browser has marked disconnected", () => {
    startPad();
    slots = [pad({ connected: false }), null, null, null];
    vi.advanceTimersByTime(300);
    expect(padDiagnostics().connected).toBe(false);
  });
});

describe("a standard pad", () => {
  it("fires each face button from its W3C index", () => {
    const hits: string[] = [];
    startPad();
    for (const name of ["a", "b", "x", "y"] as const) on(name, () => hits.push(name));
    const xbox = pad();
    slots = [xbox, null, null, null];
    vi.advanceTimersByTime(300);
    for (const i of [0, 1, 2, 3]) {
      press(xbox, i);
      vi.advanceTimersByTime(60);
      press(xbox, i, false);
      vi.advanceTimersByTime(60);
    }
    expect(hits).toEqual(["a", "b", "x", "y"]);
  });

  /** Buttons 12-15, which is where this repo's own hardware reports them. */
  it("fires each direction from the d-pad", () => {
    const hits: string[] = [];
    startPad();
    for (const name of ["up", "down", "left", "right"] as const) {
      on(name, () => hits.push(name));
    }
    const xbox = pad();
    slots = [xbox, null, null, null];
    vi.advanceTimersByTime(300);
    for (const i of [12, 13, 14, 15]) {
      press(xbox, i);
      vi.advanceTimersByTime(60);
      press(xbox, i, false);
      vi.advanceTimersByTime(60);
    }
    expect(hits).toEqual(["up", "down", "left", "right"]);
  });

  /** A held d-pad has to repeat, digitally -- see `pushFor`. */
  it("autorepeats a held direction", () => {
    const hits: string[] = [];
    startPad();
    on("down", () => hits.push("down"));
    const xbox = pad();
    slots = [xbox, null, null, null];
    vi.advanceTimersByTime(300);
    press(xbox, 13);
    vi.advanceTimersByTime(1200);
    expect(hits.length).toBeGreaterThan(3);
  });

  /**
   * Triggers are analog, and some drivers never set `pressed` on them.
   */
  it("counts a pulled trigger as pressed even with pressed unset", () => {
    const hits: string[] = [];
    startPad();
    on("r2", () => hits.push("r2"));
    const xbox = pad();
    slots = [xbox, null, null, null];
    vi.advanceTimersByTime(300);
    (xbox.buttons as unknown as GamepadButton[])[7] = {
      pressed: false,
      touched: true,
      value: 0.9,
    } as GamepadButton;
    vi.advanceTimersByTime(100);
    expect(hits).toEqual(["r2"]);
  });
});

/**
 * The layout a browser produces when it cannot vouch for the pad -- an Xbox pad
 * over Bluetooth that XInput did not claim, and most third-party pads.
 *
 * Read through the W3C indices this pad looks nearly inert, and the half that
 * matters most is the half that fails hardest: no direction works at all.
 */
describe("a non-standard pad", () => {
  function hidPad(): Gamepad {
    return pad({
      id: "045e-0b13-Xbox Wireless Controller",
      mapping: "" as GamepadMappingType,
      buttons: 15,
      // sticks, then the two trigger axes, then the hat -- centred at 1.29.
      axes: [0, 0, 0, 0, -1, -1, 1.2857],
    });
  }

  it("maps the face buttons past their gaps", () => {
    const hits: string[] = [];
    startPad();
    for (const name of ["a", "b", "x", "y"] as const) on(name, () => hits.push(name));
    const hid = hidPad();
    slots = [hid, null, null, null];
    vi.advanceTimersByTime(300);
    // A, B, X, Y at 0, 1, 3, 4 -- not 0, 1, 2, 3.
    for (const i of [0, 1, 3, 4]) {
      press(hid, i);
      vi.advanceTimersByTime(60);
      press(hid, i, false);
      vi.advanceTimersByTime(60);
    }
    expect(hits).toEqual(["a", "b", "x", "y"]);
  });

  it("drives the directions from the hat axis", () => {
    const hits: string[] = [];
    startPad();
    for (const name of ["up", "down", "left", "right"] as const) {
      on(name, () => hits.push(name));
    }
    const hid = hidPad();
    slots = [hid, null, null, null];
    vi.advanceTimersByTime(300);
    // The eight hat positions are evenly spaced across -1..1.
    for (const value of [-1, -0.4285, 0.1428, 0.7142]) {
      axis(hid, 6, value);
      vi.advanceTimersByTime(60);
      axis(hid, 6, 1.2857);
      vi.advanceTimersByTime(60);
    }
    expect(hits).toEqual(["up", "right", "down", "left"]);
  });

  it("leaves a centred hat alone", () => {
    const hits: string[] = [];
    startPad();
    for (const name of ["up", "down", "left", "right"] as const) {
      on(name, () => hits.push(name));
    }
    slots = [hidPad(), null, null, null];
    vi.advanceTimersByTime(600);
    expect(hits).toEqual([]);
  });

  /*
   * A last axis that is NOT a hat.
   *
   * Plenty of non-standard pads end on a stick, slider or gyro axis, and one
   * resting at 0 is hat position 4 -- Down. Read as a hat, it held Down from the
   * first frame: the ring auto-repeated to the bottom of the screen and no real
   * Down could ever make an edge, with nobody touching the pad.
   */
  function plainPad(rest: number): Gamepad {
    return pad({
      id: "28de-1205-Steam Deck",
      mapping: "" as GamepadMappingType,
      buttons: 15,
      axes: [0, 0, 0, rest],
    });
  }

  it.each([0, -1, 0.5])("holds no direction from a last axis resting at %s", (rest) => {
    const hits: string[] = [];
    startPad();
    for (const name of ["up", "down", "left", "right"] as const) {
      on(name, () => hits.push(name));
    }
    slots = [plainPad(rest), null, null, null];
    vi.advanceTimersByTime(1500);
    expect(hits).toEqual([]);
  });

  it("lets the arrow keys drive beside a pad whose last axis is not a hat", () => {
    const hits: string[] = [];
    startPad();
    for (const name of ["up", "down"] as const) on(name, () => hits.push(name));
    slots = [plainPad(0), null, null, null];
    vi.advanceTimersByTime(300);

    for (const key of ["ArrowDown", "ArrowUp", "ArrowDown"]) {
      window.dispatchEvent(new KeyboardEvent("keydown", { key }));
      vi.advanceTimersByTime(40);
      window.dispatchEvent(new KeyboardEvent("keyup", { key }));
      vi.advanceTimersByTime(80);
    }
    expect(hits).toEqual(["down", "up", "down"]);
  });

  it("reads the triggers from their axes", () => {
    const hits: string[] = [];
    startPad();
    on("l2", () => hits.push("l2"));
    const hid = hidPad();
    slots = [hid, null, null, null];
    vi.advanceTimersByTime(300);
    axis(hid, 5, 1);
    vi.advanceTimersByTime(100);
    expect(hits).toEqual(["l2"]);
  });
});

/**
 * The loop stalling, and getting back.
 *
 * No browser runs rAF for a hidden or occluded window, so a handle taken just
 * before the window went away sits un-run. Treating that handle as proof the
 * loop was alive made `wake()` -- the one route back -- return early, and the
 * controller stayed dead until a reload.
 */
describe("recovering a stalled loop", () => {
  it("re-arms on focus after rAF stopped running", () => {
    const hits: string[] = [];
    startPad();
    on("a", () => hits.push("a"));
    const xbox = pad();
    slots = [xbox, null, null, null];
    vi.advanceTimersByTime(300);
    expect(padDiagnostics().connected).toBe(true);

    // The window goes away: rAF stops firing and its handle is never called.
    (globalThis as unknown as Record<string, unknown>).requestAnimationFrame = () =>
      1234 as unknown as number;
    vi.advanceTimersByTime(200);

    // ...and comes back. `performance.now()` moves with the fake clock, so the
    // loop reads as stalled rather than as merely idle.
    (globalThis as unknown as Record<string, unknown>).requestAnimationFrame = (
      cb: FrameRequestCallback,
    ) => setTimeout(() => cb(performance.now()), 16) as unknown as number;
    vi.advanceTimersByTime(2000);
    window.dispatchEvent(new Event("focus"));
    vi.advanceTimersByTime(100);

    press(xbox, 0);
    vi.advanceTimersByTime(200);
    expect(hits).toEqual(["a"]);
  });
});

/**
 * The key latch, and the press that fell down the gap behind it.
 *
 * A key tapped faster than a frame is a key the poll never sees, so `keyLatch`
 * holds it until one frame has looked. That frame writes `prev` as well -- so
 * it records the key as DOWN, and only the NEXT frame can record the release.
 * With no pad connected there is nothing else to poll, so that next frame sat
 * on the 100ms idle timer... and `wake()` cancels the idle timer the instant
 * another key arrives. The second press then read `down && was`, produced no
 * edge, and was dropped in silence.
 *
 * Two taps inside a tenth of a second were one press, on the keyboard fallback
 * only -- a real pad keeps the loop at full rate and gets the release frame for
 * free, which is why this never showed up on a desk. It shows up on a Steam
 * Deck in gaming mode, where the whole controller IS the keyboard fallback.
 */
describe("two taps in quick succession", () => {
  it("fires twice, even with nothing else keeping the loop awake", () => {
    const hits: string[] = [];
    startPad();
    on("a", () => hits.push("a"));

    const tap = () => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
      vi.advanceTimersByTime(40);
      window.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter" }));
      // Well inside `IDLE_MS`, which is exactly the window that ate the second.
      vi.advanceTimersByTime(40);
    };

    tap();
    tap();
    expect(hits).toEqual(["a", "a"]);
  });

  /*
   * The other way to lose the second: the loop fired the first and has not yet
   * drawn the frame that would see it let go, and the second tap lands in
   * between. A frame is 16ms here and up to a tenth of a second on a slow
   * machine that has just rendered something heavy -- Enter opened the deck
   * catalogue, Enter on the tile it landed on took nothing, six times in six
   * on a CI runner. The key was released and pressed again, so it is a press.
   */
  it("fires twice when the second tap lands before the frame that saw the first released", () => {
    const hits: string[] = [];
    startPad();
    on("a", () => hits.push("a"));

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
    window.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter" }));
    // One frame: the press fires and is recorded as down. Not a second one.
    vi.advanceTimersByTime(17);
    expect(hits).toEqual(["a"]);

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
    window.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter" }));
    vi.advanceTimersByTime(60);
    expect(hits).toEqual(["a", "a"]);
  });
});

describe("diagnostics", () => {
  it("reports what the browser can see, not only what the app decided", () => {
    startPad();
    slots = [pad({ index: 0 }), null, null, null];
    vi.advanceTimersByTime(300);
    const d = padDiagnostics();
    expect(d.listening).toBe(true);
    expect(d.supported).toBe(true);
    expect(d.pads[0]).toContain("standard");
    expect(d.pads[0]).toContain("17 buttons");
  });

  it("says so when the browser has no Gamepad API at all", () => {
    (navigator as unknown as Record<string, unknown>).getGamepads = undefined;
    startPad();
    vi.advanceTimersByTime(300);
    expect(padDiagnostics().supported).toBe(false);
    expect(padDiagnostics().pads).toEqual([]);
  });
});

/**
 * Analog motion is input, even before it becomes a direction.
 *
 * The mode was noted on a button EDGE only, which missed the two things a player
 * does most: nudging a stick short of the fire threshold, and HOLDING a trigger.
 * A hold produces no edges at all for as long as it lasts, so keeping the region
 * dial up left the hint bar advertising `Enter` and `Esc` to somebody visibly
 * holding a controller.
 */
describe("what counts as using the pad", () => {
  it("notices a stick pushed short of the fire threshold", () => {
    const one = pad();
    slots[0] = one;
    startPad();
    vi.advanceTimersByTime(20);
    expect(getInputMode()).toBe("mouse");

    // Past the deadzone, well short of `STICK.fire` -- so no direction fires and
    // the edge path never runs.
    axis(one, 0, 0.4);
    vi.advanceTimersByTime(40);
    expect(getInputMode()).toBe("pad");
  });

  it("notices a trigger held, which produces no edges at all", () => {
    const one = pad();
    slots[0] = one;
    startPad();
    vi.advanceTimersByTime(20);
    resetInputMode();

    press(one, 6);
    vi.advanceTimersByTime(40);
    expect(getInputMode()).toBe("pad");
  });

  it("says nothing about a pad sitting at rest", () => {
    // A controller in the room is not a controller in your hands -- the whole
    // reason the mode is last-input-wins rather than is-one-plugged-in.
    slots[0] = pad();
    startPad();
    vi.advanceTimersByTime(200);
    expect(getInputMode()).toBe("mouse");
  });
});
