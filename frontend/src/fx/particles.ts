/**
 * The particle simulation.
 *
 * Pure: no canvas, no DOM, no `requestAnimationFrame`. It owns a fixed pool of
 * particles and a `step(dt)`, and `ParticleLayer` is the only thing that knows
 * how to draw one. That split is what makes an explosion testable -- a test
 * steps the field sixty times and asserts on where the embers ended up, with no
 * rendering context anywhere near it.
 *
 * ## Why a pool
 *
 * A wrath emits six bursts at once and each burst is dozens of particles. Doing
 * that with fresh objects would allocate a few thousand short-lived objects
 * inside one frame and hand the garbage collector a spike at exactly the moment
 * the board is busiest. The pool is allocated once and reused forever; `alive`
 * is the only thing that changes.
 *
 * When the pool is full, new emissions are **dropped rather than growing it**.
 * A capped effect that thins out under load is a board that keeps its frame
 * rate; an uncapped one is a slideshow precisely when the game is at its most
 * dramatic. Recycling the oldest instead would make a big burst eat the smaller
 * ones that caused it.
 */

/** Deterministic in tests, `Math.random` in the app. */
export type Rng = () => number;

export type Shape = "spark" | "ember" | "shard" | "smoke" | "ring" | "mote";

export interface Particle {
  alive: boolean;
  shape: Shape;
  x: number;
  y: number;
  vx: number;
  vy: number;
  /** Seconds lived, and the total it gets. Alpha and size are curves on these. */
  age: number;
  ttl: number;
  size: number;
  rot: number;
  spin: number;
  /** Velocity retained per second: 0.1 is thick air, 0.9 is nearly frictionless. */
  drag: number;
  /** Pixels per second squared. Negative floats upward. */
  gravity: number;
  /** Colour, held as components so alpha can be composed per frame. */
  r: number;
  g: number;
  b: number;
  alpha: number;
  /** Additive blending. Embers and sparks glow; smoke and shards do not. */
  glow: boolean;
}

/**
 * How to emit one family of particles.
 *
 * Ranges are `[min, max]` and sampled uniformly. A preset (see `presets.ts`) is
 * one or more of these; an explosion is embers *and* smoke *and* a shockwave,
 * which is why `emit` takes a list rather than a single spec.
 */
export interface EmitSpec {
  shape: Shape;
  count: number;
  /** Initial speed, px/sec. */
  speed: [number, number];
  /** Direction window in radians. Defaults to the full circle. */
  angle?: [number, number];
  ttl: [number, number];
  size: [number, number];
  spin?: [number, number];
  drag?: number;
  gravity?: number;
  /** Colours to pick between, as `[r, g, b]`. */
  colors: [number, number, number][];
  alpha?: number;
  glow?: boolean;
  /** Spawn offset from the emission point, px. Gives a burst some width. */
  spread?: number;
}

/**
 * The ceiling.
 *
 * Sized for the worst honest case: a six-permanent wrath is six `explode`
 * presets at ~70 particles each, and the board should still have room for the
 * combat that caused it.
 */
export const CAP = 600;

function pick<T>(rng: Rng, items: T[]): T {
  return items[Math.min(items.length - 1, Math.floor(rng() * items.length))];
}

function between(rng: Rng, range: [number, number]): number {
  return range[0] + rng() * (range[1] - range[0]);
}

function blank(): Particle {
  return {
    alive: false,
    shape: "ember",
    x: 0,
    y: 0,
    vx: 0,
    vy: 0,
    age: 0,
    ttl: 0,
    size: 0,
    rot: 0,
    spin: 0,
    drag: 0.5,
    gravity: 0,
    r: 255,
    g: 255,
    b: 255,
    alpha: 1,
    glow: true,
  };
}

export class ParticleField {
  readonly particles: Particle[];
  private cursor = 0;
  private live = 0;
  private readonly rng: Rng;

  constructor(rng: Rng = Math.random, cap: number = CAP) {
    this.particles = Array.from({ length: cap }, blank);
    this.rng = rng;
  }

  get count(): number {
    return this.live;
  }

  /**
   * The next free slot, or null when the pool is full.
   *
   * A rotating cursor rather than a scan from zero: emissions arrive in bursts
   * and the slots just behind the cursor are the ones most recently filled, so
   * starting where the last one finished finds a free slot in O(1) in the
   * common case instead of walking the whole pool for every particle.
   */
  private free(): Particle | null {
    const pool = this.particles;
    for (let i = 0; i < pool.length; i += 1) {
      const slot = pool[(this.cursor + i) % pool.length];
      if (!slot.alive) {
        this.cursor = (this.cursor + i + 1) % pool.length;
        return slot;
      }
    }
    return null;
  }

  /** Emit one or more families at a point. Silently thins out when full. */
  emit(specs: EmitSpec[], x: number, y: number, scale = 1): void {
    const rng = this.rng;
    for (const spec of specs) {
      const [lo, hi] = spec.angle ?? [0, Math.PI * 2];
      for (let i = 0; i < Math.round(spec.count * scale); i += 1) {
        const slot = this.free();
        if (!slot) return;

        const angle = lo + rng() * (hi - lo);
        const speed = between(rng, spec.speed) * scale;
        const spread = (spec.spread ?? 0) * scale;
        const [r, g, b] = pick(rng, spec.colors);

        slot.alive = true;
        slot.shape = spec.shape;
        slot.x = x + (rng() * 2 - 1) * spread;
        slot.y = y + (rng() * 2 - 1) * spread;
        slot.vx = Math.cos(angle) * speed;
        slot.vy = Math.sin(angle) * speed;
        slot.age = 0;
        slot.ttl = between(rng, spec.ttl);
        slot.size = between(rng, spec.size) * scale;
        slot.rot = rng() * Math.PI * 2;
        slot.spin = spec.spin ? between(rng, spec.spin) : 0;
        slot.drag = spec.drag ?? 0.5;
        slot.gravity = spec.gravity ?? 0;
        slot.r = r;
        slot.g = g;
        slot.b = b;
        slot.alpha = spec.alpha ?? 1;
        slot.glow = spec.glow ?? true;
        this.live += 1;
      }
    }
  }

  /**
   * Advance by `dt` milliseconds.
   *
   * Drag is applied as `retained ** seconds` rather than as a per-frame
   * multiply, so a burst decays identically at 30fps and at 144fps. The frame
   * loop already clamps `dt`, but a field stepped directly in a test can be
   * handed anything, so the exponent is the honest form either way.
   */
  step(dt: number): void {
    const seconds = dt / 1000;
    if (seconds <= 0) return;

    for (const p of this.particles) {
      if (!p.alive) continue;

      p.age += seconds;
      if (p.age >= p.ttl) {
        p.alive = false;
        this.live -= 1;
        continue;
      }

      const kept = p.drag ** seconds;
      p.vx *= kept;
      p.vy = p.vy * kept + p.gravity * seconds;
      p.x += p.vx * seconds;
      p.y += p.vy * seconds;
      p.rot += p.spin * seconds;
    }
  }

  /** Kill everything. Between games, and when narration is skipped. */
  clear(): void {
    for (const p of this.particles) p.alive = false;
    this.live = 0;
  }
}

/**
 * How faded a particle is, 1 → 0 across its life.
 *
 * Shared by the renderer and by tests so "has it finished" has one definition.
 * Sparks and embers hold their brightness and then drop away late; smoke fades
 * from the moment it appears. Ring is the shockwave and vanishes fastest.
 */
export function opacityOf(p: Particle): number {
  const t = p.ttl <= 0 ? 1 : Math.min(1, p.age / p.ttl);
  switch (p.shape) {
    case "smoke":
      return p.alpha * (1 - t) * 0.9;
    case "ring":
      return p.alpha * (1 - t) ** 2;
    case "mote":
      // Fades in as well as out: a mote appearing at full brightness reads as a
      // dot switching on rather than as something coming apart.
      return p.alpha * Math.sin(t * Math.PI);
    default:
      return p.alpha * (t < 0.7 ? 1 : (1 - t) / 0.3);
  }
}

/** Drawn size at the current age. Smoke and shockwaves expand; the rest do not. */
export function sizeOf(p: Particle): number {
  const t = p.ttl <= 0 ? 1 : Math.min(1, p.age / p.ttl);
  switch (p.shape) {
    case "smoke":
      return p.size * (1 + t * 1.8);
    case "ring":
      return p.size * (1 + t * 5);
    default:
      return p.size;
  }
}
