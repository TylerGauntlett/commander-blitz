/**
 * The particle simulation, tested without a canvas.
 *
 * That split is the reason `fx/particles.ts` owns no rendering: an explosion is
 * a physics question -- how many, how fast, how long, where do they end up --
 * and every one of those is answerable by stepping the field and reading it.
 * The drawing is `ParticleLayer`'s, and there is nothing in it worth asserting
 * that a story cannot show you better.
 */

import { describe, expect, it } from "vitest";
import { CAP, opacityOf, ParticleField, sizeOf } from "../src/fx/particles";
import { explode, impact, shatter } from "../src/fx/presets";

/** A fixed sequence, so a burst is the same burst every run. */
function seeded(seed = 1): () => number {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 4294967296;
    return state / 4294967296;
  };
}

function field(): ParticleField {
  return new ParticleField(seeded());
}

describe("ParticleField", () => {
  it("starts empty and fills on emit", () => {
    const f = field();
    expect(f.count).toBe(0);
    f.emit(impact(), 100, 100);
    expect(f.count).toBeGreaterThan(0);
  });

  it("puts every particle at the emission point, within the spec's spread", () => {
    const f = field();
    f.emit(impact(), 400, 250);
    for (const p of f.particles) {
      if (!p.alive) continue;
      expect(Math.abs(p.x - 400)).toBeLessThanOrEqual(10);
      expect(Math.abs(p.y - 250)).toBeLessThanOrEqual(10);
    }
  });

  it("empties itself once everything has outlived its ttl", () => {
    const f = field();
    f.emit(impact(), 0, 0);
    // The longest ttl in any preset here is well under two seconds.
    for (let i = 0; i < 200; i += 1) f.step(16);
    expect(f.count).toBe(0);
  });

  it("never grows past the cap, and stays usable when it hits one", () => {
    const f = field();
    // Far more than a wrath's worth: twenty explosions at once.
    for (let i = 0; i < 20; i += 1) f.emit(explode(), i * 10, 0);
    expect(f.count).toBeLessThanOrEqual(CAP);
    // Thinning out is the designed behaviour, not an error state: the field
    // must still step and still drain.
    for (let i = 0; i < 200; i += 1) f.step(16);
    expect(f.count).toBe(0);
  });

  it("recycles slots, so a second burst after a first still emits", () => {
    const f = field();
    for (let i = 0; i < 20; i += 1) f.emit(explode(), 0, 0);
    for (let i = 0; i < 200; i += 1) f.step(16);
    f.emit(impact(), 50, 50);
    expect(f.count).toBeGreaterThan(0);
  });

  /**
   * The one that would silently rot.
   *
   * Drag is `retained ** seconds`, not a per-frame multiply, so a burst has to
   * decay to the same place whether the machine drew it in four steps or in
   * forty. A per-frame multiply passes every other test in this file and makes
   * the board's effects subtly different on every display.
   */
  it("decays the same at 30fps and at 144fps", () => {
    const coarse = new ParticleField(seeded());
    const fine = new ParticleField(seeded());
    // `explode` rather than `impact`: its embers live most of a second, so
    // there is still something in flight to compare after 300ms.
    coarse.emit(explode(), 0, 0);
    fine.emit(explode(), 0, 0);

    for (let i = 0; i < 9; i += 1) coarse.step(1000 / 30);
    for (let i = 0; i < 43; i += 1) fine.step(1000 / 144);

    // The same seed emits the same particles into the same slots, so comparing
    // by index compares one particle with itself at two frame rates.
    const pairs = coarse.particles
      .map((p, i) => [p, fine.particles[i]] as const)
      .filter(([a, b]) => a.alive && b.alive);
    expect(pairs.length).toBeGreaterThan(0);

    for (const [a, b] of pairs) {
      // ~300ms of travel; a few pixels apart is integration error, not a bug.
      expect(Math.abs(a.x - b.x)).toBeLessThan(6);
      expect(Math.abs(a.y - b.y)).toBeLessThan(6);
    }
  });

  it("ignores a zero or negative step", () => {
    const f = field();
    f.emit(impact(), 0, 0);
    const before = f.particles.filter((p) => p.alive).map((p) => p.x);
    f.step(0);
    f.step(-16);
    expect(f.particles.filter((p) => p.alive).map((p) => p.x)).toEqual(before);
  });

  it("clears on demand", () => {
    const f = field();
    f.emit(explode(), 0, 0);
    f.clear();
    expect(f.count).toBe(0);
  });

  it("aims a directed impact along the angle it was given", () => {
    const f = new ParticleField(seeded());
    f.emit(impact(0), 0, 0, 1); // straight right
    f.step(50);
    const moving = f.particles.filter((p) => p.alive && p.shape === "spark");
    expect(moving.length).toBeGreaterThan(0);
    // The fan is +/- 0.7rad around the angle, so every spark carries rightward.
    for (const p of moving) expect(p.vx).toBeGreaterThan(0);
  });

  it("scales a burst without changing its shape", () => {
    const small = new ParticleField(seeded());
    const big = new ParticleField(seeded());
    small.emit(impact(), 0, 0, 1);
    big.emit(impact(), 0, 0, 2);
    expect(big.count).toBeGreaterThan(small.count);
  });
});

describe("the draw curves", () => {
  it("fades everything to nothing by the end of its life", () => {
    const f = field();
    f.emit(explode(), 0, 0);
    for (const p of f.particles) {
      if (!p.alive) continue;
      p.age = p.ttl;
      expect(opacityOf(p)).toBeLessThanOrEqual(0.001);
    }
  });

  it("expands smoke and shockwaves, and only those", () => {
    const f = field();
    f.emit(explode(), 0, 0);
    for (const p of f.particles) {
      if (!p.alive) continue;
      const born = sizeOf(p);
      p.age = p.ttl * 0.9;
      const late = sizeOf(p);
      if (p.shape === "smoke" || p.shape === "ring") expect(late).toBeGreaterThan(born);
      else expect(late).toBe(born);
    }
  });

  it("gives shards gravity so glass falls rather than floating", () => {
    const f = field();
    f.emit(shatter(), 0, 0);
    const shard = f.particles.find((p) => p.alive && p.shape === "shard");
    expect(shard?.gravity).toBeGreaterThan(0);
  });
});
