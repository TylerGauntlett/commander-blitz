/**
 * The particle presets, one story each.
 *
 * These exist to be *looked at*. Every number in `fx/presets.ts` -- how many
 * embers, how fast, how long they live, how hard they fall -- is a judgement
 * that can only really be made by watching it, and watching it inside the real
 * game means casting a spell and hoping something dies at a moment you happen
 * to be paying attention. Here a burst is a button.
 *
 * All of them opt into `motion: "real"`. That flag now does two jobs: it stops
 * Framer holding transforms still, *and* it clears the reduced-motion override
 * that `fx/reducedMotion.ts` reads -- headless Chromium reports
 * `prefers-reduced-motion: reduce`, and `burst()` honours it, so without the
 * opt-in every one of these would render a blank canvas.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { useEffect, useRef } from "react";
import { expect, waitFor } from "storybook/test";
import type { PresetName } from "../../fx/presets";
import { burst, clearParticles, ParticleLayer, particleCount } from "./ParticleLayer";

/**
 * A board-shaped box with the layer over it, firing on an interval.
 *
 * Repeating rather than one-shot: a burst is over in under a second, and a
 * story you have to reload to see again is a story nobody tunes against.
 */
function Stage({
  preset,
  angle,
  scale = 1,
  every = 1200,
}: {
  preset: PresetName;
  angle?: number;
  scale?: number;
  every?: number;
}) {
  const boardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    clearParticles();
    const box = boardRef.current?.getBoundingClientRect();
    const at = { x: (box?.width ?? 600) / 2, y: (box?.height ?? 400) / 2 };
    const fire = () => burst(preset, at, { angle, scale });
    // A frame's grace so the layer has measured itself before the first shot.
    const first = window.setTimeout(fire, 60);
    const timer = window.setInterval(fire, every);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
      clearParticles();
    };
  }, [preset, angle, scale, every]);

  return (
    <div
      ref={boardRef}
      data-fx-origin
      style={{
        position: "relative",
        height: "70vh",
        background: "var(--bg-board, #17131f)",
        borderRadius: 12,
        overflow: "hidden",
      }}
    >
      <ParticleLayer boardRef={boardRef} />
    </div>
  );
}

const meta = {
  title: "Game/ParticleLayer",
  component: Stage,
  parameters: {
    layout: "fullscreen",
    automtg: { mount: "bare", motion: "real" },
  },
} satisfies Meta<typeof Stage>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A creature connecting. The commonest effect on the board by a distance. */
export const Impact: Story = {
  args: { preset: "impact" },
  play: async () => {
    await waitFor(() => expect(particleCount()).toBeGreaterThan(0));
  },
};

/** The same hit, aimed: combat points it along the attacker's line of travel. */
export const DirectedImpact: Story = {
  args: { preset: "impact", angle: 0, scale: 1.6 },
};

/** A permanent destroyed: shockwave, embers thrown out, smoke left behind. */
export const Explode: Story = {
  args: { preset: "explode", every: 1600 },
};

/** A countered spell. Breaks rather than burns, and falls under gravity. */
export const Shatter: Story = {
  args: { preset: "shatter", every: 1600 },
};

/** Exile: it does not fall, it comes apart and goes up. */
export const Dissolve: Story = {
  args: { preset: "dissolve", every: 1600 },
};

/** A permanent landing. Deliberately the quietest thing here. */
export const Dust: Story = {
  args: { preset: "dust", every: 900 },
};

/** Ambient drift: a trigger going on the stack. */
export const Motes: Story = {
  args: { preset: "motes", every: 1100 },
};

/** Life gained, in the same rising shape as `motes`. */
export const Heal: Story = {
  args: { preset: "heal", every: 1100 },
};

/**
 * A wrath: six deaths at once.
 *
 * The load case the pool cap was sized for. What to look for is that it still
 * moves -- the field thins new emissions out rather than growing, so a board
 * this busy should drop particles, not frames.
 */
export const Wrath: Story = {
  args: { preset: "explode", every: 2000 },
  decorators: [
    (Story) => {
      const ref = useRef<HTMLDivElement>(null);
      useEffect(() => {
        const box = ref.current?.getBoundingClientRect();
        const w = box?.width ?? 900;
        const fire = () => {
          for (let i = 0; i < 6; i += 1) {
            burst("explode", { x: (w / 7) * (i + 1), y: 180 + (i % 2) * 120 });
          }
        };
        const timer = window.setInterval(fire, 2000);
        const first = window.setTimeout(fire, 120);
        return () => {
          window.clearInterval(timer);
          window.clearTimeout(first);
        };
      }, []);
      return (
        <div ref={ref}>
          <Story />
        </div>
      );
    },
  ],
};
