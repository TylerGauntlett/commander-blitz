/**
 * The canvas the board explodes onto.
 *
 * Everything else that flies over the table is a React element with a timer on
 * it (`FxLayer`), and that is the right shape for six numerals -- but a single
 * destroyed permanent throws seventy particles, and a wrath throws four
 * hundred. As DOM nodes that is four hundred elements mounted, laid out,
 * composited and unmounted inside one second, on a board that already carries
 * ninety cards with drop shadows. So the physical effects get a canvas instead:
 * one element, one context, no layout.
 *
 * The field is a **module singleton** rather than component state. An effect is
 * emitted from wherever the thing happened -- a beat handler, a combat
 * choreography, a card actuator's follow-through -- and threading a ref from
 * `Table` down to each of those would put a rendering concern in the signature
 * of every one of them. `burst()` is importable from anywhere; this component
 * is only what draws the result.
 *
 * The loop stops when the field empties. An idle board costs nothing, which is
 * the same rule `fx/scheduler.ts` and `CombatArrows` already follow.
 */

import { useEffect, useRef } from "react";
import { opacityOf, ParticleField, sizeOf } from "../../fx/particles";
import { impact, PRESETS, type PresetName } from "../../fx/presets";
import { prefersReducedMotion } from "../../fx/reducedMotion";
import { onFrame } from "../../fx/scheduler";

/** Board-relative, matching `FxLayer`'s anchors and `CombatArrows`' origin. */
export interface Point {
  x: number;
  y: number;
}

const field = new ParticleField();

/** Set by the mounted layer; `burst` is a no-op until something can draw it. */
let wake: (() => void) | null = null;

/**
 * Throw a preset at a point on the board.
 *
 * `angle` directs an `impact` along the line the hit came in on -- see
 * `presets.impact`. `scale` is for weight: a 12-point hit should not look like
 * a 1-point one, and scaling the recipe is cheaper and more legible than
 * authoring a second preset per magnitude.
 */
export function burst(
  name: PresetName,
  at: Point,
  opts: { angle?: number; scale?: number } = {},
): void {
  // Reduced motion keeps the numerals, captions and flashes -- the things that
  // say *what happened* -- and drops the things that only say how it felt.
  if (prefersReducedMotion()) return;
  const specs = name === "impact" ? impact(opts.angle ?? null) : PRESETS[name]();
  field.emit(specs, at.x, at.y, opts.scale ?? 1);
  wake?.();
}

/** Drop every particle. Narration skip and game teardown. */
export function clearParticles(): void {
  field.clear();
}

/** For tests and the perf trace. */
export function particleCount(): number {
  return field.count;
}

function draw(ctx: CanvasRenderingContext2D, width: number, height: number): void {
  ctx.clearRect(0, 0, width, height);

  // Two passes rather than one, so the composite mode is set twice per frame
  // instead of once per particle. Smoke and shards also *must* come first:
  // they are the things embers are meant to glow in front of.
  for (const pass of [false, true]) {
    ctx.globalCompositeOperation = pass ? "lighter" : "source-over";
    for (const p of field.particles) {
      if (!p.alive || p.glow !== pass) continue;
      const alpha = opacityOf(p);
      if (alpha <= 0.01) continue;
      const size = sizeOf(p);
      ctx.fillStyle = `rgba(${p.r}, ${p.g}, ${p.b}, ${alpha})`;

      switch (p.shape) {
        case "spark": {
          // Drawn along its own velocity, so a spark is a streak pointing the
          // way it is going. A dot here reads as a firework; a streak reads as
          // something struck hard enough to throw fragments.
          const speed = Math.hypot(p.vx, p.vy) || 1;
          const len = size;
          ctx.strokeStyle = ctx.fillStyle;
          ctx.lineWidth = Math.max(1, size * 0.16);
          ctx.lineCap = "round";
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(p.x - (p.vx / speed) * len, p.y - (p.vy / speed) * len);
          ctx.stroke();
          break;
        }
        case "shard": {
          ctx.save();
          ctx.translate(p.x, p.y);
          ctx.rotate(p.rot);
          ctx.fillRect(-size / 2, -size / 4, size, size / 2);
          ctx.restore();
          break;
        }
        case "ring": {
          ctx.strokeStyle = ctx.fillStyle;
          ctx.lineWidth = Math.max(1, 5 * (1 - p.age / p.ttl));
          ctx.beginPath();
          ctx.arc(p.x, p.y, size, 0, Math.PI * 2);
          ctx.stroke();
          break;
        }
        default: {
          ctx.beginPath();
          ctx.arc(p.x, p.y, size, 0, Math.PI * 2);
          ctx.fill();
          break;
        }
      }
    }
  }
  ctx.globalCompositeOperation = "source-over";
}

interface Props {
  /** The element the canvas covers; particle coordinates are relative to it. */
  boardRef: React.RefObject<HTMLElement | null>;
}

export function ParticleLayer({ boardRef }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const board = boardRef.current;
    if (!canvas || !board) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return; // jsdom, and any context-less environment. Sim still runs.

    let width = 0;
    let height = 0;
    let running = false;

    /*
     * Backing store at device resolution, CSS box at layout resolution.
     *
     * Without the DPR scale a spark is a soft grey smear on every laptop
     * display, which is the one shape here that depends on being a crisp line.
     */
    const resize = () => {
      const box = board.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      width = box.width;
      height = box.height;
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const start = () => {
      if (running) return;
      running = true;
      onFrame((dt) => {
        field.step(dt);
        draw(ctx, width, height);
        if (field.count > 0) return true;
        // One last clear, so the final frame's fading particles are erased
        // rather than left painted on a canvas nobody is updating any more.
        ctx.clearRect(0, 0, width, height);
        running = false;
        return false;
      });
    };

    wake = start;
    resize();

    const observer = new ResizeObserver(resize);
    observer.observe(board);

    return () => {
      observer.disconnect();
      if (wake === start) wake = null;
      field.clear();
    };
  }, [boardRef]);

  /*
   * The wrapper is what carries `aria-hidden`, not the canvas.
   *
   * Sparks and smoke are pure decoration and must not reach the accessibility
   * tree -- the numerals and captions in `.fx` are what say what happened. But
   * a `<canvas>` counts as an interactive element, so hiding it directly (or
   * giving it `role="presentation"`) is the kind of markup that is usually a
   * mistake, and the linter is right to say so. A plain div has neither problem.
   */
  return (
    <div className="fx-particles" aria-hidden="true" data-testid="particle-layer">
      <canvas ref={canvasRef} />
    </div>
  );
}
