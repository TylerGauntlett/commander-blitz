/**
 * The one frame loop, and the card actuators that ride on it.
 *
 * Both are pure timing machines with no React in them, which is exactly why
 * they had no tests: nothing renders, so nothing was there to assert against.
 * On a timer-backed `requestAnimationFrame` (see `tests/setup.ts`) and a fake
 * clock, every rule the scheduler's header states is checkable frame by frame
 * (TECH_DEBT CG-02).
 */

import { motionValue } from "motion/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { drive, register, restAll } from "../src/fx/actuators";
import { onFrame, overTime, stopAll, tickerCount } from "../src/fx/scheduler";

const FRAME = 16;

beforeEach(() => {
  vi.useFakeTimers();
  // A timer-backed frame on the fake clock, so `advanceTimersByTime` is frames.
  globalThis.requestAnimationFrame = (cb: FrameRequestCallback) =>
    setTimeout(() => cb(performance.now()), FRAME) as unknown as number;
  globalThis.cancelAnimationFrame = (h: number) =>
    clearTimeout(h as unknown as ReturnType<typeof setTimeout>);
});

afterEach(() => {
  stopAll();
  restAll();
  vi.useRealTimers();
});

describe("scheduler", () => {
  it("does not run when nothing is subscribed, and stops once everything is done", () => {
    expect(tickerCount()).toBe(0);
    const ticks: number[] = [];
    onFrame((dt) => {
      ticks.push(dt);
      return ticks.length < 3;
    });
    expect(tickerCount()).toBe(1);
    vi.advanceTimersByTime(FRAME * 10);
    expect(ticks.length).toBe(3);
    expect(tickerCount()).toBe(0);
    // No frame is pending once the last ticker returned false.
    expect(vi.getTimerCount()).toBe(0);
  });

  it("clamps a long gap so a restored tab does not teleport everything", () => {
    const seen: number[] = [];
    onFrame((dt) => {
      seen.push(dt);
      return seen.length < 2;
    });
    // The first frame arrives on time; the second after a "minute" away.
    vi.advanceTimersByTime(FRAME);
    vi.setSystemTime(Date.now() + 60_000);
    vi.advanceTimersByTime(FRAME);
    expect(seen.every((dt) => dt <= 64)).toBe(true);
  });

  it("drops a ticker that throws, without taking the others down", () => {
    let survivorFrames = 0;
    onFrame(() => {
      throw new Error("boom");
    });
    onFrame(() => {
      survivorFrames += 1;
      return survivorFrames < 2;
    });
    vi.advanceTimersByTime(FRAME * 4);
    expect(survivorFrames).toBe(2);
    expect(tickerCount()).toBe(0);
  });

  it("lets a ticker subscribe another without running it a frame early", () => {
    const order: string[] = [];
    onFrame(() => {
      order.push("parent");
      onFrame(() => {
        order.push("child");
        return false;
      });
      return false;
    });
    vi.advanceTimersByTime(FRAME);
    expect(order).toEqual(["parent"]);
    vi.advanceTimersByTime(FRAME);
    expect(order).toEqual(["parent", "child"]);
  });

  it("overTime runs 0 -> 1 and drops itself on the frame it arrives", () => {
    const ts: number[] = [];
    overTime(FRAME * 4, (t) => ts.push(t));
    vi.advanceTimersByTime(FRAME * 8);
    expect(ts.at(-1)).toBe(1);
    expect(ts.every((t, i) => i === 0 || t >= ts[i - 1])).toBe(true);
    expect(tickerCount()).toBe(0);
  });

  it("overTime with no duration completes at once, and the manual cancel unsubscribes", () => {
    const ts: number[] = [];
    overTime(0, (t) => ts.push(t));
    expect(ts).toEqual([1]);
    const cancel = onFrame(() => true);
    expect(tickerCount()).toBe(1);
    cancel();
    expect(tickerCount()).toBe(0);
  });

  it("stopAll clears every subscriber and the pending frame", () => {
    onFrame(() => true);
    onFrame(() => true);
    stopAll();
    expect(tickerCount()).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("actuators", () => {
  function card(oid: number, left = 100, top = 100) {
    const el = document.createElement("div");
    el.setAttribute("data-oid", String(oid));
    el.getBoundingClientRect = () =>
      ({ left, top, width: 80, height: 112, right: left + 80, bottom: top + 112 }) as DOMRect;
    document.body.appendChild(el);
    const channel = {
      x: motionValue(0),
      y: motionValue(0),
      rotate: motionValue(0),
      scale: motionValue(1),
    };
    const release = register(oid, channel);
    return { channel, release };
  }

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("hands out an actuator only for a registered card", () => {
    expect(drive(1)).toBeNull();
    const { release } = card(1);
    expect(drive(1)).not.toBeNull();
    release();
    expect(drive(1)).toBeNull();
  });

  it("lunges toward a point and comes all the way back to rest", () => {
    const { channel } = card(1);
    drive(1)?.lunge({ x: 500, y: 100 }, { ms: FRAME * 10 });
    vi.advanceTimersByTime(FRAME * 4);
    // Out, to the right, tilted into the swing, slightly larger.
    expect(channel.x.get()).toBeGreaterThan(0);
    expect(channel.rotate.get()).toBeGreaterThan(0);
    expect(channel.scale.get()).toBeGreaterThan(1);
    vi.advanceTimersByTime(FRAME * 12);
    expect(channel.x.get()).toBe(0);
    expect(channel.y.get()).toBe(0);
    expect(channel.rotate.get()).toBe(0);
    expect(channel.scale.get()).toBe(1);
    expect(tickerCount()).toBe(0);
  });

  it("leans toward a point and STAYS there until rested", () => {
    const { channel } = card(1);
    drive(1)?.lean({ x: 500, y: 100 }, { ms: FRAME * 4 });
    vi.advanceTimersByTime(FRAME * 10);
    expect(channel.x.get()).toBeGreaterThan(0);
    expect(channel.x.get()).toBeLessThanOrEqual(14);
    expect(tickerCount()).toBe(0);
    drive(1)?.rest();
    expect(channel.x.get()).toBe(0);
    expect(channel.scale.get()).toBe(1);
  });

  it("recoils away from a point, shudders in place, and pulses, each settling", () => {
    const { channel } = card(1);
    drive(1)?.recoil({ x: 0, y: 100 }, 1);
    vi.advanceTimersByTime(FRAME * 2);
    expect(channel.x.get()).toBeGreaterThan(0); // knocked to the right, away from x=0
    vi.advanceTimersByTime(400);
    expect(channel.x.get()).toBe(0);

    drive(1)?.shudder(1);
    vi.advanceTimersByTime(FRAME * 3);
    expect(Math.abs(channel.x.get())).toBeGreaterThan(0);
    vi.advanceTimersByTime(400);
    expect(channel.x.get()).toBe(0);

    drive(1)?.pulse();
    vi.advanceTimersByTime(140);
    expect(channel.scale.get()).toBeGreaterThan(1);
    vi.advanceTimersByTime(400);
    expect(channel.scale.get()).toBe(1);
  });

  it("does not stack: a new effect cancels the one running and settles first", () => {
    const { channel } = card(1);
    drive(1)?.lunge({ x: 500, y: 100 }, { ms: 1000 });
    vi.advanceTimersByTime(FRAME * 6);
    expect(channel.x.get()).toBeGreaterThan(0);
    drive(1)?.shudder(0.5);
    // One ticker, not two.
    expect(tickerCount()).toBe(1);
  });

  it("restAll puts every card back and drops every effect", () => {
    const a = card(1, 100, 100);
    const b = card(2, 300, 100);
    drive(1)?.lunge({ x: 500, y: 100 }, { ms: 1000 });
    drive(2)?.lean({ x: 500, y: 100 });
    vi.advanceTimersByTime(FRAME * 4);
    restAll();
    expect(a.channel.x.get()).toBe(0);
    expect(b.channel.x.get()).toBe(0);
    expect(tickerCount()).toBe(0);
  });

  it("skips a card that is not in the document", () => {
    const channel = {
      x: motionValue(0),
      y: motionValue(0),
      rotate: motionValue(0),
      scale: motionValue(1),
    };
    register(9, channel);
    drive(9)?.lunge({ x: 500, y: 100 });
    drive(9)?.lean({ x: 500, y: 100 });
    drive(9)?.recoil({ x: 0, y: 0 }, 1);
    expect(tickerCount()).toBe(0);
    expect(channel.x.get()).toBe(0);
  });
});
