/**
 * The bargain between a text field and the ring, and the one Enter path.
 *
 * Two defects live here and both of them ended a controller session outright,
 * which is why they get their own file rather than a corner of `pad.test.ts`:
 * that file is about turning a real `Gamepad` into presses, and these are about
 * what happens to a KEY once it has been turned into one.
 *
 * ## The field was a one-way door
 *
 * Off the board every stop is a native control (`stops.ts:stopsIn`), so the
 * ring walks onto the seat-name box, the pod code box and the deck search box
 * in the ordinary course of moving around. The old guard was "a field keeps
 * every key", so once the ring was in one, every arrow went to the caret and
 * none to navigation. A desktop has Tab; a Steam Deck does not, and Tab is
 * swallowed anyway -- so reaching your own name was the end of the screen.
 *
 * The rule now is the one every console text field uses: a direction is the
 * caret's while the caret has somewhere to go that way, and the ring's at the
 * end of the line.
 *
 * ## Enter did everything twice
 *
 * `useCursorNav` implements A as "click the element the ring is on", and
 * `cursor.ts` puts real DOM focus on that same element -- so the browser
 * activated it as well. One press chose a deck AND pressed whatever the ring
 * re-resolved onto afterwards. `SWALLOW` now carries `Enter` and the listener
 * runs in the capture phase, so the ring's path is the only path.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetInputMode } from "../src/input/inputMode";
import { on, resetPad, startPad } from "../src/input/pad";

/** rAF on the fake clock, so a press can be stepped to the frame that fires it. */
beforeEach(() => {
  vi.useFakeTimers();
  (navigator as unknown as { getGamepads: () => unknown[] }).getGamepads = () => [];
  (globalThis as unknown as Record<string, unknown>).requestAnimationFrame = (
    cb: FrameRequestCallback,
  ) => setTimeout(() => cb(performance.now()), 16) as unknown as number;
  (globalThis as unknown as Record<string, unknown>).cancelAnimationFrame = (h: number) =>
    clearTimeout(h as unknown as ReturnType<typeof setTimeout>);
  document.body.innerHTML = "";
});

afterEach(() => {
  resetPad();
  resetInputMode();
  vi.useRealTimers();
  document.body.innerHTML = "";
});

/** A text field with a caret somewhere in it. */
function field(value: string, at: number, kind: "input" | "textarea" = "input") {
  const el = document.createElement(kind);
  el.value = value;
  document.body.append(el);
  el.focus();
  el.setSelectionRange(at, at);
  return el;
}

/**
 * One key, pressed and released, from a given element.
 *
 * Dispatched on the element rather than on `window` because the guard reads
 * `event.target` -- a `window`-dispatched event has no `tagName` and would sail
 * straight past the very check under test.
 */
function tap(el: Element | Window, key: string): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  el.dispatchEvent(event);
  el.dispatchEvent(new KeyboardEvent("keyup", { key, bubbles: true }));
  return event;
}

/** What the pad layer heard, in order. */
function listen(...names: ("a" | "up" | "down" | "left" | "right")[]): string[] {
  const heard: string[] = [];
  startPad();
  for (const name of names) on(name, () => heard.push(name));
  return heard;
}

describe("a direction, with a caret in the way", () => {
  it("leaves the field on Down, because a single line has nowhere below it", () => {
    const heard = listen("down");
    tap(field("Player 1", 4), "ArrowDown");
    vi.advanceTimersByTime(100);
    expect(heard).toEqual(["down"]);
  });

  it("leaves the field on Up for the same reason", () => {
    const heard = listen("up");
    tap(field("Player 1", 4), "ArrowUp");
    vi.advanceTimersByTime(100);
    expect(heard).toEqual(["up"]);
  });

  it("gives Left to the caret while there is text behind it", () => {
    const heard = listen("left");
    tap(field("Player 1", 4), "ArrowLeft");
    vi.advanceTimersByTime(100);
    expect(heard).toEqual([]);
  });

  it("gives Left to the ring at column zero", () => {
    const heard = listen("left");
    tap(field("Player 1", 0), "ArrowLeft");
    vi.advanceTimersByTime(100);
    expect(heard).toEqual(["left"]);
  });

  it("gives Right to the ring at the end of the value", () => {
    const heard = listen("right");
    tap(field("Player 1", 8), "ArrowRight");
    vi.advanceTimersByTime(100);
    expect(heard).toEqual(["right"]);
  });

  it("preventDefaults the arrow it takes, so the caret does not also jump", () => {
    listen("down");
    const event = tap(field("Player 1", 4), "ArrowDown");
    expect(event.defaultPrevented).toBe(true);
  });

  it("leaves an arrow the field kept alone", () => {
    listen("left");
    const event = tap(field("Player 1", 4), "ArrowLeft");
    expect(event.defaultPrevented).toBe(false);
  });

  it("keeps a selection for the field -- collapsing a range is its job", () => {
    const heard = listen("left");
    const el = field("Player 1", 0);
    el.setSelectionRange(0, 4);
    tap(el, "ArrowLeft");
    vi.advanceTimersByTime(100);
    expect(heard).toEqual([]);
  });

  it("gives a textarea Up while there is a line above the caret", () => {
    const heard = listen("up");
    // Caret on the second line.
    tap(field("one\ntwo", 5, "textarea"), "ArrowUp");
    vi.advanceTimersByTime(100);
    expect(heard).toEqual([]);
  });

  it("lets a textarea go on the line that has none above it", () => {
    const heard = listen("up");
    tap(field("one\ntwo", 1, "textarea"), "ArrowUp");
    vi.advanceTimersByTime(100);
    expect(heard).toEqual(["up"]);
  });
});

describe("everything that is not a direction", () => {
  it("still belongs to the field -- `a`/`d` are letters here, not the d-pad", () => {
    const heard = listen("left", "right");
    const el = field("Player 1", 4);
    tap(el, "a");
    tap(el, "d");
    vi.advanceTimersByTime(100);
    expect(heard).toEqual([]);
  });

  it("still lets Enter commit a name rather than pressing the ring's stop", () => {
    const heard = listen("a");
    const el = field("Player 1", 8);
    const event = tap(el, "Enter");
    vi.advanceTimersByTime(100);
    expect(heard).toEqual([]);
    // And it is not swallowed, or the field's own submit handler never runs.
    expect(event.defaultPrevented).toBe(false);
  });
});

describe("Enter, outside a field", () => {
  it("reaches the ring and is swallowed, so the browser cannot also activate", () => {
    const heard = listen("a");
    const button = document.createElement("button");
    document.body.append(button);
    button.focus();
    const event = tap(button, "Enter");
    vi.advanceTimersByTime(100);
    expect(heard).toEqual(["a"]);
    expect(event.defaultPrevented).toBe(true);
  });

  /**
   * The half that needed the capture phase.
   *
   * `preventDefault` stops the browser's own activation of a `<button>` and
   * does nothing at all about a `div[role="button"]` carrying its own
   * `Enter` handler -- which is what a board card, a chair's card and a deck
   * tile all are, because a `<button>` may not contain the divs a card face is
   * made of. Listening at capture and stopping propagation is what makes those
   * one path rather than two.
   */
  it("never reaches a stop's own key handler", () => {
    listen("a");
    const tile = document.createElement("div");
    tile.setAttribute("role", "button");
    tile.tabIndex = 0;
    const own: string[] = [];
    tile.addEventListener("keydown", () => own.push("own"));
    document.body.append(tile);
    tile.focus();
    tap(tile, "Enter");
    vi.advanceTimersByTime(100);
    expect(own).toEqual([]);
  });

  it("still lets a key nobody swallowed through to a listener", () => {
    // Escape is `B` and several overlays close on it with their own `window`
    // handler; stopping propagation there would break every one of them.
    listen("a");
    const seen: string[] = [];
    window.addEventListener("keydown", (event) => seen.push(event.key));
    const button = document.createElement("button");
    document.body.append(button);
    tap(button, "Escape");
    expect(seen).toEqual(["Escape"]);
  });
});
