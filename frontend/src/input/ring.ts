/**
 * The focus ring, sprung.
 *
 * Two boxes follow the cursor: `#ring`, and `#ringtrail` -- one softer follower
 * whose opacity is driven by speed, which is what makes a fast sweep legible
 * instead of a strobe. Neither draws the *outline*: `[data-cursor]` carries
 * that itself, so the ring is correct the instant the attribute moves and stays
 * correct if this module never runs at all. These two are the travel.
 *
 * THE LOOP STOPS WHEN IT SETTLES. This is a battery-powered 7-inch computer; a
 * rAF that never stops costs play time for nothing. It also runs on its *own*
 * rAF rather than `fx/scheduler.ts`'s, because `scheduler.stopAll()` is called
 * on teardown between games and the ring must not be droppable by an FX reset.
 */

import { prefersReducedMotion } from "../fx/reducedMotion";

/**
 * TUNED IN TIME, NOT IN STIFFNESS, because time is the thing being judged.
 *
 * `w` is the natural frequency in rad/s and `z` the damping ratio, so the two
 * numbers a review actually cares about fall straight out of them:
 *
 *     settling time ~= 4 / (z*w)        overshoot = e^(-pi*z / sqrt(1 - z^2))
 *
 * `full` (w 36, z 0.78) is a 142ms settling time and 2.0% of overshoot -- and,
 * the number that actually matters because it is when the eye calls it arrived,
 * WITHIN 2px OF TARGET IN 117ms ON A 200px HOP. That is a hair quicker than a
 * 150ms CSS transition, so the ring is not slower than the thing it improves
 * on, and the 2% is what makes it read as *landing* rather than as stopping.
 *
 * `swift` (w 52, z 0.85) is 90ms, for the animation setting that halves every
 * other wait in the game. Reduced motion is no spring at all -- see
 * `retargetRing`, which snaps rather than selecting a third profile.
 */
export const SPRING = {
  full: { w: 36, z: 0.78 },
  swift: { w: 52, z: 0.85 },
} as const;

/** The trail's follow time constant, in seconds. */
export const TRAIL_TAU = 0.062;
/** px/s impulse when a direction has nowhere to go. */
export const NUDGE = 340;
/** Anything further than this starts its travel from this far out. See `longHop`. */
export const LONG_HOP = 420;

export interface SpringState {
  x: number;
  v: number;
}

/**
 * The analytic step, and why it is not `v += (k*dx - d*v) * dt`.
 *
 * The obvious integrator is one line and it is wrong in two ways that both
 * matter on this hardware. It is FRAME-RATE DEPENDENT -- the same spring
 * overshoots 1.6px at 60fps and 4.5px at 144fps, so the ring is a different
 * ring on a monitor than on the Deck's 60Hz panel. And it goes UNSTABLE at
 * large `dt`, which is exactly what a backgrounded or thermally-throttled tab
 * hands you; a `dt` clamp is a patch over that rather than an answer to it.
 *
 * The closed form of a damped harmonic oscillator has neither problem. Six
 * lines, EXACT for any `dt`, and at a huge `dt` the decay term goes to zero by
 * itself -- so a dropped second resolves to "the ring is where the cursor is",
 * which is the correct picture rather than a launch across the screen.
 *
 * `tests/ringSpring.test.ts` pins the frame-rate independence directly: one
 * 16ms step must equal four 4ms steps.
 */
export function springStep(
  x: number,
  v: number,
  target: number,
  w: number,
  z: number,
  dt: number,
): SpringState {
  const wd = w * Math.sqrt(1 - z * z);
  const a = x - target;
  const b = (v + z * w * a) / wd;
  const e = Math.exp(-z * w * dt);
  const c = Math.cos(wd * dt);
  const s = Math.sin(wd * dt);
  const body = a * c + b * s;
  return { x: target + e * body, v: e * (wd * (b * c - a * s) - z * w * body) };
}

/** A box, in viewport coordinates. */
export interface RingBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Cut the distance of a long hop, keep its direction.
 *
 * `L1`/`R1` jump zones, and a zone jump can be most of the screen. Teleporting
 * loses the only thing the travel was for -- a jump is exactly when you most
 * need telling where the ring went, because you did not walk it there. But
 * flying it loses it a different way: a spring's settling time does not depend
 * on distance, so a 1000px hop arrives in the same ~140ms as a 200px one, at a
 * peak around 13,000 px/s. At 60Hz that is 220px between frames -- four frames
 * of a rectangle appearing in unrelated places, which is a teleport with extra
 * steps and a worse one, because it strobes across everything between.
 *
 * So anything further than `LONG_HOP` starts from exactly that far out along
 * the line it would have come in on. Every hop gets the same arrival and the
 * same readable entry from the correct side. The size comes with it: a ring
 * still the width of the card it left would spend the whole hop being the
 * wrong shape for both ends of it.
 *
 * Pure, and returns the shortened start box, or `null` when the hop is already
 * short enough to fly whole.
 */
export function longHop(from: RingBox, to: RingBox, limit = LONG_HOP): RingBox | null {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const d = Math.hypot(dx, dy);
  if (d <= limit || d === 0) return null;
  const k = limit / d;
  return {
    x: to.x - dx * k,
    y: to.y - dy * k,
    w: to.w - (to.w - from.w) * k,
    h: to.h - (to.h - from.h) * k,
  };
}

// --------------------------------------------------------------------- state

type Axis = "x" | "y" | "w" | "h";
const AXES: readonly Axis[] = ["x", "y", "w", "h"];

const RING = {
  x: 0,
  y: 0,
  w: 0,
  h: 0,
  vx: 0,
  vy: 0,
  vw: 0,
  vh: 0,
  tx: 0,
  ty: 0,
  tw: 0,
  th: 0,
  // The trail, following at its own pace.
  gx: 0,
  gy: 0,
  gw: 0,
  gh: 0,
  /** False until the first cursor has been measured. */
  placed: false,
  /** Screen + overlay; a change means teleport rather than spring. */
  ctx: "",
  /** The tilt of the thing the ring is around, in degrees. See `paint`. */
  angle: 0,
  raf: 0,
  last: 0,
  speed: 0,
};

const vel = (a: Axis): "vx" | "vy" | "vw" | "vh" => `v${a}` as const;
const tgt = (a: Axis): "tx" | "ty" | "tw" | "th" => `t${a}` as const;

/** `swift` while the game is playing back at `instant`; otherwise `full`. */
let profile: keyof typeof SPRING = "full";

export function setRingProfile(next: keyof typeof SPRING): void {
  profile = next;
}

/** Test seam: the module is a singleton and stories mount repeatedly. */
export function resetRing(): void {
  for (const a of AXES) {
    RING[a] = 0;
    RING[vel(a)] = 0;
    RING[tgt(a)] = 0;
  }
  RING.gx = 0;
  RING.gy = 0;
  RING.gw = 0;
  RING.gh = 0;
  RING.placed = false;
  RING.ctx = "";
  RING.speed = 0;
  if (RING.raf) cancelAnimationFrame(RING.raf);
  RING.raf = 0;
  RING.last = 0;
}

/**
 * Start the loop if it is not already running.
 *
 * `last` is cleared HERE and only here, because this is the only place that
 * knows the loop was idle -- a continuing flight must keep its previous
 * timestamp or `dt` collapses to the nominal 1/60 every frame and the whole
 * point of the closed form goes with it. `frame` re-queues itself directly for
 * exactly that reason.
 */
function wake(): void {
  if (RING.raf) return;
  RING.last = 0;
  RING.raf = requestAnimationFrame(frame);
}

/**
 * At rest, exactly on target, and so is everything that follows it.
 *
 * One function because every caller that wants this wants ALL of it: a partial
 * snap that leaves a velocity behind is how the trail gets stranded.
 */
function snap(): void {
  for (const a of AXES) {
    RING[a] = RING[tgt(a)];
    RING[vel(a)] = 0;
  }
  RING.gx = RING.x;
  RING.gy = RING.y;
  RING.gw = RING.w;
  RING.gh = RING.h;
  RING.speed = 0;
  paint();
}

function frame(now: number): void {
  RING.raf = 0;
  // The first frame after a wake has no previous timestamp to subtract. No
  // clamp is needed on the rest: the closed form is exact at any dt.
  const dt = RING.last ? (now - RING.last) / 1000 : 1 / 60;
  RING.last = now;

  const s = SPRING[profile];
  let moving = false;
  for (const a of AXES) {
    const next = springStep(RING[a], RING[vel(a)], RING[tgt(a)], s.w, s.z, dt);
    RING[a] = next.x;
    RING[vel(a)] = next.v;
    if (Math.abs(RING[tgt(a)] - RING[a]) > 0.3 || Math.abs(RING[vel(a)]) > 4) {
      moving = true;
    }
  }
  if (!moving) {
    for (const a of AXES) {
      RING[a] = RING[tgt(a)];
      RING[vel(a)] = 0;
    }
  }

  const follow = 1 - Math.exp(-dt / TRAIL_TAU);
  RING.gx += (RING.x - RING.gx) * follow;
  RING.gy += (RING.y - RING.gy) * follow;
  RING.gw += (RING.w - RING.gw) * follow;
  RING.gh += (RING.h - RING.gh) * follow;

  RING.speed = Math.hypot(RING.vx, RING.vy);
  paint();
  // Re-queued here rather than through `wake()`, which would clear `last`.
  if (moving) RING.raf = requestAnimationFrame(frame);
  else RING.last = 0;
}

function paint(): void {
  const ring = document.getElementById("ring");
  if (!ring) return;
  ring.style.left = `${RING.x.toFixed(1)}px`;
  ring.style.top = `${RING.y.toFixed(1)}px`;
  ring.style.width = `${Math.max(0, RING.w).toFixed(1)}px`;
  ring.style.height = `${Math.max(0, RING.h).toFixed(1)}px`;
  /*
   * THE RING TILTS WITH WHAT IT IS AROUND.
   *
   * A hand card is rotated by the arc, and `getBoundingClientRect` is
   * axis-aligned -- so the ring was a big upright box around a tilted card,
   * touching it at two corners and standing well clear of it at the other two.
   * On the one surface a controller player spends a main phase in.
   *
   * Set rather than sprung: the ANGLE changes only when the ring moves between
   * two cards, and the position is already springing between them. A second
   * spring on the rotation reads as a wobble rather than as travel.
   */
  ring.style.transform = RING.angle ? `rotate(${RING.angle.toFixed(2)}deg)` : "";
  const trail = document.getElementById("ringtrail");
  if (!trail) return;
  trail.style.left = `${RING.gx.toFixed(1)}px`;
  trail.style.top = `${RING.gy.toFixed(1)}px`;
  trail.style.width = `${Math.max(0, RING.gw).toFixed(1)}px`;
  trail.style.height = `${Math.max(0, RING.gh).toFixed(1)}px`;
  trail.style.transform = RING.angle ? `rotate(${RING.angle.toFixed(2)}deg)` : "";
  trail.style.opacity = Math.min(0.5, RING.speed / 2600).toFixed(3);
}

/** The four numbers `retargetRing` needs. A `DOMRect` satisfies it. */
export interface RingRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * WHAT SHAPE IS THE THING THE RING IS AROUND.
 *
 * `getBoundingClientRect` answers "what box does this occupy on screen", which
 * for a rotated element is its axis-aligned envelope -- wider and shorter than
 * the element, and upright. A hand card is tilted by the arc, so the ring stood
 * clear of it at two corners and cut it at the other two, on the surface a
 * controller player spends a main phase in.
 *
 * So the rect is rebuilt from the element's own untransformed size, scaled and
 * centred on the envelope's centre, and the rotation is handed to `paint` to
 * apply. The centre is the one thing the envelope reports exactly, whatever the
 * transform.
 *
 * THE TRANSFORM IS ACCUMULATED UP THE TREE, because the rotation is rarely on
 * the stop itself: the hand rotates `.hand__lift`, which is the card's parent.
 * The walk stops at the board for the same reason the clip walk in
 * `input/stops.ts` walks at all -- it is bounded, it is cheap, and it runs once
 * per press rather than per frame.
 *
 * Rotations and scales compose additively and multiplicatively only while there
 * is no skew, which is true of every transform this app writes: `rotate`,
 * `scale`, and translations, which do not affect either.
 */
export function ringTargetFor(el: HTMLElement): { rect: RingRect; angle: number } {
  const box = el.getBoundingClientRect();
  const upright = { rect: box, angle: 0 };
  if (typeof DOMMatrixReadOnly === "undefined") return upright;

  let radians = 0;
  let sx = 1;
  let sy = 1;
  for (let node: HTMLElement | null = el; node; node = node.parentElement) {
    const transform = getComputedStyle(node).transform;
    if (!transform || transform === "none") {
      if (node.classList.contains("table")) break;
      continue;
    }
    let m: DOMMatrixReadOnly;
    try {
      m = new DOMMatrixReadOnly(transform);
    } catch {
      return upright;
    }
    radians += Math.atan2(m.b, m.a);
    sx *= Math.hypot(m.a, m.b) || 1;
    sy *= Math.hypot(m.c, m.d) || 1;
    if (node.classList.contains("table")) break;
  }

  const degrees = (radians * 180) / Math.PI;
  // Nothing to correct: skip the rebuild so an untransformed stop keeps
  // measuring exactly as it always did.
  if (Math.abs(degrees) < 0.01) return upright;

  const w = el.offsetWidth * sx;
  const h = el.offsetHeight * sy;
  if (w <= 0 || h <= 0) return upright;

  return {
    rect: {
      left: box.left + box.width / 2 - w / 2,
      top: box.top + box.height / 2 - h / 2,
      width: w,
      height: h,
    },
    angle: degrees,
  };
}

/** Padding between the measured box and the ring drawn around it. */
const PAD = 3;

/**
 * Tell the spring where the cursor went.
 *
 * `context` is the screen and overlay the stop lives on. A SPRING ACROSS A
 * SCREEN CHANGE IS A SPRING ACROSS NOTHING -- flying the ring from a seat in
 * the lobby to a card on the board is 600px of travel between two things that
 * were never on screen together, and it reads as a glitch rather than as
 * movement. Same context, spring; new context, teleport.
 */
export function retargetRing(rect: RingRect | null, context: string, angle = 0): void {
  const ring = document.getElementById("ring");
  if (!ring) return;
  if (!rect) {
    ring.classList.remove("ring--on");
    RING.placed = false;
    return;
  }
  RING.angle = angle;
  RING.tx = rect.left - PAD;
  RING.ty = rect.top - PAD;
  RING.tw = rect.width + PAD * 2;
  RING.th = rect.height + PAD * 2;

  if (!RING.placed || context !== RING.ctx) {
    snap();
  } else {
    const start = longHop(
      { x: RING.x, y: RING.y, w: RING.w, h: RING.h },
      { x: RING.tx, y: RING.ty, w: RING.tw, h: RING.th },
    );
    if (start) {
      RING.x = start.x;
      RING.y = start.y;
      RING.w = start.w;
      RING.h = start.h;
      RING.gx = start.x;
      RING.gy = start.y;
      RING.gw = start.w;
      RING.gh = start.h;
    }
  }
  RING.placed = true;
  RING.ctx = context;
  ring.classList.add("ring--on");

  /*
   * Reduced motion is not "a faster spring", it is NO spring: the ring is
   * simply where the cursor is. The trail has to be zeroed with it -- its
   * opacity is read from `speed`, and a speed left over from the last
   * full-motion flight would strand a glowing rectangle on screen that nothing
   * would ever come back to clear.
   */
  if (prefersReducedMotion()) {
    snap();
    return;
  }
  // Paint the current position now rather than waiting for the next rAF: a
  // freshly mounted `#ring` has no inline geometry, and one frame of a
  // full-opacity ring at 0,0 is a flash in the corner on every mount.
  paint();
  wake();
}

/** An impulse into a wall the ring cannot cross. */
export function ringNudge(dir: "up" | "down" | "left" | "right"): void {
  if (prefersReducedMotion() || !RING.placed) return;
  if (dir === "left") RING.vx -= NUDGE;
  else if (dir === "right") RING.vx += NUDGE;
  else if (dir === "up") RING.vy -= NUDGE;
  else RING.vy += NUDGE;
  wake();
}

/**
 * An impulse on the SIZE: the ring squeezes onto what you pressed and recovers.
 *
 * Written as velocity rather than as a class so the re-render `A` is about to
 * cause cannot interrupt it. Width and height are measured from the top-left,
 * so shrinking them alone squeezes the ring toward its own left edge -- which
 * looks like the ring slipping rather than like the thing being pushed. Half
 * the impulse goes into the origin so the squeeze is centred on the card.
 */
export function ringPress(): void {
  if (prefersReducedMotion() || !RING.placed) return;
  RING.vw -= 300;
  RING.vx += 150;
  RING.vh -= 300;
  RING.vy += 150;
  wake();
}
