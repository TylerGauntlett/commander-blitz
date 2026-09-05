/**
 * The synthesised sound palette, against a fake Web Audio graph.
 *
 * jsdom has no `AudioContext`, which is the first thing worth pinning: `play`
 * must be a silent no-op there, and everywhere else a broken audio stack must
 * never take the narration queue down with it. With a stand-in context every
 * voice can be run once to prove it builds its graph and starts its sources --
 * the failure this catches is a voice that throws, which today would be
 * swallowed and simply never heard (TECH_DEBT CG-02).
 */

import { afterEach, describe, expect, it, vi } from "vitest";

/** A parameter that records what was scheduled on it. */
function param(value = 0) {
  return {
    value,
    setValueAtTime: vi.fn(),
    linearRampToValueAtTime: vi.fn(),
    exponentialRampToValueAtTime: vi.fn(),
    cancelScheduledValues: vi.fn(),
  };
}

/** A node whose `connect` chains, as the real one does. */
function node(extra: Record<string, unknown> = {}) {
  const n: Record<string, unknown> = { connect: vi.fn((to: unknown) => to), ...extra };
  return n;
}

class FakeAudioContext {
  static made: FakeAudioContext[] = [];
  sampleRate = 48_000;
  currentTime = 1;
  state = "suspended";
  destination = node();
  resume = vi.fn(async () => undefined);
  started: string[] = [];
  gains = 0;
  constructor() {
    FakeAudioContext.made.push(this);
  }
  createGain() {
    this.gains += 1;
    return node({ gain: param(1) });
  }
  createBuffer(_channels: number, frames: number) {
    return { getChannelData: () => new Float32Array(frames) };
  }
  createConvolver() {
    return node({ buffer: null });
  }
  createBufferSource() {
    return node({
      buffer: null,
      start: vi.fn(() => this.started.push("noise")),
      stop: vi.fn(),
    });
  }
  createBiquadFilter() {
    return node({ type: "lowpass", frequency: param(), Q: param() });
  }
  createOscillator() {
    return node({
      type: "sine",
      frequency: param(),
      start: vi.fn(() => this.started.push("tone")),
      stop: vi.fn(),
    });
  }
}

/** A fresh module each time: `sfx` remembers its context and its failure. */
async function fresh() {
  vi.resetModules();
  return import("../src/audio/sfx");
}

afterEach(() => {
  vi.unstubAllGlobals();
  FakeAudioContext.made = [];
});

describe("play", () => {
  it("is a silent no-op where there is no Web Audio at all", async () => {
    vi.stubGlobal("AudioContext", undefined);
    const sfx = await fresh();
    expect(() => sfx.play("drop")).not.toThrow();
    expect(() => sfx.play("deny")).not.toThrow();
  });

  it("builds one context on first use, resumes it, and reuses it", async () => {
    vi.stubGlobal("AudioContext", FakeAudioContext);
    const sfx = await fresh();
    sfx.play("drop");
    sfx.play("deny");
    expect(FakeAudioContext.made).toHaveLength(1);
    const c = FakeAudioContext.made[0];
    // Autoplay policy parks the context; every play asks for it back.
    expect(c.resume).toHaveBeenCalled();
    // Master, dry and wet busses, then a voice envelope per source.
    expect(c.gains).toBeGreaterThanOrEqual(3 + 2);
    expect(c.started.length).toBeGreaterThan(0);
  });

  it("gives up for good when the context cannot be built, without throwing", async () => {
    class Refusing {
      constructor() {
        throw new Error("no audio");
      }
    }
    vi.stubGlobal("AudioContext", Refusing);
    const sfx = await fresh();
    expect(() => sfx.play("drop")).not.toThrow();
    expect(() => sfx.play("drop")).not.toThrow();
  });

  it("survives a voice that throws mid-graph", async () => {
    class Exploding extends FakeAudioContext {
      createOscillator(): never {
        throw new Error("no oscillator");
      }
    }
    vi.stubGlobal("AudioContext", Exploding);
    const sfx = await fresh();
    expect(() => sfx.play("deny")).not.toThrow();
  });

  it("every voice in the palette starts at least one source", async () => {
    vi.stubGlobal("AudioContext", FakeAudioContext);
    const sfx = await fresh();
    const names: Parameters<typeof sfx.play>[0][] = [
      "thump",
      "hit",
      "tap",
      "shuffle",
      "chime",
      "toll",
      "impact",
      "boom",
      "whoosh",
      "shatter",
      "pickup",
      "drop",
      "deny",
      "move",
      "back",
    ];
    const silent: string[] = [];
    let before = 0;
    for (const name of names) {
      sfx.play(name);
      const now = FakeAudioContext.made[0].started.length;
      if (now === before) silent.push(name);
      before = now;
    }
    expect(silent, "voices that made no sound").toEqual([]);
  });
});
