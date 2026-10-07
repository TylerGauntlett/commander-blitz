/**
 * The right stick scrolls whatever the ring is on: the reader for a card, the
 * surrounding list for anything else -- and never moves the ring.
 *
 * jsdom lays nothing out, so every box here is given the two numbers that make
 * it "overflowing" by hand. That is the whole of what `scrollsY` reads.
 */

import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetInputMode } from "../src/input/inputMode";
import { resetPad, startPad } from "../src/input/pad";

const cursor = vi.hoisted(() => ({ stop: null as string | null, refollow: vi.fn() }));
vi.mock("../src/input/cursor", () => ({
  getCursor: () => cursor.stop,
  refollowCursor: cursor.refollow,
}));

const { SCROLL_SPEED, scrollStep, scrollTargetFor, useStickScroll } = await import(
  "../src/input/stickScroll"
);

function el(selector: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(selector);
  if (!found) throw new Error(`no ${selector}`);
  return found;
}

/** Give `el` more content than box, and make it a scroller. */
function overflowing(el: HTMLElement, scroll = 600, client = 200): HTMLElement {
  el.style.overflowY = "auto";
  Object.defineProperty(el, "scrollHeight", { configurable: true, value: scroll });
  Object.defineProperty(el, "clientHeight", { configurable: true, value: client });
  return el;
}

/** The reader with overflowing rules text, a lane with a card, an action list. */
function board(): { rules: HTMLElement; lane: HTMLElement; list: HTMLElement } {
  document.body.innerHTML = `
    <section data-testid="card-preview"><div class="reader__rules">Long text</div></section>
    <div class="lane"><div data-stop="card:14">Bear</div></div>
    <div class="actions"><button data-stop="act:7">Cast</button></div>
  `;
  const rules = overflowing(el(".reader__rules"));
  const lane = overflowing(el(".lane"));
  const list = overflowing(el(".actions"));
  return { rules, lane, list };
}

afterEach(() => {
  document.body.innerHTML = "";
  cursor.stop = null;
  cursor.refollow.mockReset();
});

describe("which box it scrolls", () => {
  it("scrolls a held card's rules first, wherever the ring is", () => {
    board();
    document.body.insertAdjacentHTML(
      "beforeend",
      '<div data-testid="card-hold"><div class="face__rules">Long text</div></div>',
    );
    const held = overflowing(el('[data-testid="card-hold"] .face__rules'));
    expect(scrollTargetFor("card:14")).toBe(held);
    expect(scrollTargetFor("act:7")).toBe(held);
    expect(scrollTargetFor(null)).toBe(held);
  });

  it("scrolls the reader when the ring is on a card", () => {
    const { rules } = board();
    expect(scrollTargetFor("card:14")).toBe(rules);
  });

  it("never the lane the card sits in, which would carry the card off", () => {
    const { lane } = board();
    expect(scrollTargetFor("card:14")).not.toBe(lane);
  });

  it("nothing on a card whose text fits", () => {
    const { rules } = board();
    overflowing(rules, 200, 200);
    expect(scrollTargetFor("card:14")).toBeNull();
  });

  it("scrolls the list around an action", () => {
    const { list } = board();
    expect(scrollTargetFor("act:7")).toBe(list);
  });

  it("skips a box that has nothing to scroll for the one around it", () => {
    document.body.innerHTML = `
      <div class="outer"><div class="inner"><button data-stop="act:7">Cast</button></div></div>
    `;
    const outer = overflowing(el(".outer"));
    overflowing(el(".inner"), 100, 100);
    expect(scrollTargetFor("act:7")).toBe(outer);
  });

  it("nothing without a ring", () => {
    board();
    expect(scrollTargetFor(null)).toBeNull();
  });
});

describe("how far", () => {
  it("is signed: up scrolls up", () => {
    expect(scrollStep(-1, 0.05)).toBeLessThan(0);
    expect(scrollStep(1, 0.05)).toBeGreaterThan(0);
  });

  it("is full speed at full deflection", () => {
    expect(scrollStep(1, 1 / 20)).toBeCloseTo(SCROLL_SPEED / 20);
  });

  it("is gentle on a light push", () => {
    expect(Math.abs(scrollStep(0.3, 0.05))).toBeLessThan(scrollStep(1, 0.05) / 5);
  });

  it("does not leap after a stalled frame", () => {
    expect(scrollStep(1, 5)).toBeCloseTo(scrollStep(1, 0.1));
  });
});

describe("against a pad", () => {
  let axes = [0, 0, 0, 0];

  beforeEach(() => {
    vi.useFakeTimers();
    axes = [0, 0, 0, 0];
    const pad = {
      id: "Xbox Wireless Controller (STANDARD GAMEPAD)",
      index: 0,
      connected: true,
      mapping: "standard",
      timestamp: 0,
      axes,
      buttons: Array.from({ length: 17 }, () => ({ pressed: false, touched: false, value: 0 })),
    };
    (navigator as unknown as { getGamepads: () => unknown[] }).getGamepads = () => [pad];
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

  it("pushing down scrolls the reader down and leaves the ring where it is", () => {
    const { rules, lane } = board();
    cursor.stop = "card:14";
    startPad();
    renderHook(() => useStickScroll());
    axes[3] = 1;
    vi.advanceTimersByTime(300);
    expect(rules.scrollTop).toBeGreaterThan(0);
    expect(lane.scrollTop).toBe(0);
    expect(cursor.stop).toBe("card:14");
  });

  it("scrolls an action list and tells the ring to follow its stop", () => {
    const { list } = board();
    cursor.stop = "act:7";
    startPad();
    renderHook(() => useStickScroll());
    axes[3] = 1;
    vi.advanceTimersByTime(300);
    expect(list.scrollTop).toBeGreaterThan(0);
    expect(cursor.refollow).toHaveBeenCalled();
    expect(cursor.stop).toBe("act:7");
  });

  it("a stick at rest scrolls nothing", () => {
    const { rules } = board();
    cursor.stop = "card:14";
    startPad();
    renderHook(() => useStickScroll());
    vi.advanceTimersByTime(300);
    expect(rules.scrollTop).toBe(0);
  });
});
