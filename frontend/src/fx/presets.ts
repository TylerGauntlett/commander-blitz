/**
 * The effect vocabulary, as particle recipes.
 *
 * One entry per thing that can happen to a permanent. Kept as data rather than
 * as code so the whole palette can be read at once and tuned in Storybook
 * without touching the simulation -- which is the same reason `audio/sfx.ts`
 * holds its voices as parameter blocks.
 *
 * Colours are the theme's own signal tokens (`theme.css`, "Signals"), so a
 * death burst is the same red as an attacking rim and exile is the same violet
 * as the ability rune. Effects that invent their own palette are how a board
 * stops looking like one board.
 */

import type { EmitSpec } from "./particles";

const RED: [number, number, number] = [255, 92, 92];
const EMBER: [number, number, number] = [255, 107, 94];
const GOLD: [number, number, number] = [255, 212, 121];
const WHITE: [number, number, number] = [255, 250, 235];
const GREEN: [number, number, number] = [110, 231, 160];
const BLUE: [number, number, number] = [88, 182, 255];
const VIOLET: [number, number, number] = [195, 155, 255];
const SMOKE: [number, number, number] = [58, 52, 78];
const ASH: [number, number, number] = [120, 112, 140];

/** Straight down, in radians, for the shard fan. */
const DOWNWARD: [number, number] = [Math.PI * 0.15, Math.PI * 0.85];
/** Straight up, for anything that rises. */
const UPWARD: [number, number] = [Math.PI * 1.15, Math.PI * 1.85];

export type PresetName =
  | "impact"
  | "explode"
  | "shatter"
  | "dissolve"
  | "dust"
  | "motes"
  | "heal";

/**
 * A directional spark fan.
 *
 * `impact` takes an angle so a hit reads as coming *from* somewhere: combat
 * points it along the attacker's line of travel, and a burn spell leaves it
 * radial. That single parameter is most of what makes a collision look like a
 * collision rather than a firework.
 */
export function impact(angle: number | null = null): EmitSpec[] {
  const fan: [number, number] | undefined =
    angle === null ? undefined : [angle - 0.7, angle + 0.7];
  return [
    {
      shape: "spark",
      count: 14,
      speed: [220, 620],
      angle: fan,
      ttl: [0.18, 0.34],
      size: [7, 16],
      drag: 0.02,
      colors: [WHITE, GOLD, EMBER],
      glow: true,
      spread: 3,
    },
    {
      shape: "ember",
      count: 8,
      speed: [90, 300],
      angle: fan,
      ttl: [0.25, 0.45],
      size: [2, 4],
      drag: 0.08,
      gravity: 420,
      colors: [GOLD, EMBER],
      glow: true,
    },
    {
      shape: "ring",
      count: 1,
      speed: [0, 0],
      ttl: [0.24, 0.24],
      size: [10, 10],
      drag: 1,
      colors: [WHITE],
      alpha: 0.75,
      glow: true,
    },
  ];
}

/** A permanent being destroyed: shockwave, embers thrown out, smoke left behind. */
export function explode(): EmitSpec[] {
  return [
    {
      shape: "ring",
      count: 1,
      speed: [0, 0],
      ttl: [0.34, 0.34],
      size: [16, 16],
      drag: 1,
      colors: [EMBER],
      alpha: 0.9,
      glow: true,
    },
    {
      shape: "spark",
      count: 18,
      speed: [260, 700],
      ttl: [0.22, 0.42],
      size: [8, 20],
      drag: 0.03,
      colors: [WHITE, GOLD, EMBER],
      glow: true,
      spread: 6,
    },
    {
      shape: "ember",
      count: 22,
      speed: [120, 430],
      ttl: [0.45, 0.95],
      size: [2, 5],
      drag: 0.12,
      gravity: 640,
      colors: [EMBER, RED, GOLD],
      glow: true,
      spread: 8,
    },
    {
      shape: "smoke",
      count: 10,
      speed: [40, 150],
      ttl: [0.6, 1.1],
      size: [14, 30],
      drag: 0.06,
      gravity: -70,
      colors: [SMOKE, ASH],
      alpha: 0.5,
      glow: false,
      spread: 10,
    },
  ];
}

/** A countered spell, or anything that should read as breaking rather than burning. */
export function shatter(): EmitSpec[] {
  return [
    {
      shape: "shard",
      count: 16,
      speed: [180, 520],
      angle: DOWNWARD,
      ttl: [0.5, 0.85],
      size: [5, 13],
      spin: [-9, 9],
      drag: 0.35,
      gravity: 1500,
      colors: [BLUE, WHITE],
      glow: false,
      spread: 8,
    },
    {
      shape: "spark",
      count: 8,
      speed: [200, 460],
      ttl: [0.14, 0.26],
      size: [6, 12],
      drag: 0.05,
      colors: [WHITE, BLUE],
      glow: true,
    },
  ];
}

/** Exile: it does not burn, it comes apart and goes up. */
export function dissolve(): EmitSpec[] {
  return [
    {
      shape: "mote",
      count: 26,
      speed: [30, 130],
      angle: UPWARD,
      ttl: [0.6, 1.2],
      size: [2, 5],
      drag: 0.5,
      gravity: -180,
      colors: [WHITE, VIOLET],
      glow: true,
      spread: 16,
    },
    {
      shape: "ring",
      count: 1,
      speed: [0, 0],
      ttl: [0.4, 0.4],
      size: [12, 12],
      drag: 1,
      colors: [VIOLET],
      alpha: 0.6,
      glow: true,
    },
  ];
}

/** A permanent landing: a low puff, nothing dramatic. */
export function dust(): EmitSpec[] {
  return [
    {
      shape: "smoke",
      count: 7,
      speed: [70, 190],
      angle: [Math.PI * 0.9, Math.PI * 2.1],
      ttl: [0.3, 0.55],
      size: [7, 15],
      drag: 0.04,
      gravity: -30,
      colors: [ASH, SMOKE],
      alpha: 0.4,
      glow: false,
      spread: 10,
    },
  ];
}

/** Ambient drift: a trigger going on the stack, a commander in its zone. */
export function motes(): EmitSpec[] {
  return [
    {
      shape: "mote",
      count: 12,
      speed: [20, 80],
      angle: UPWARD,
      ttl: [0.5, 1.0],
      size: [2, 4],
      drag: 0.6,
      gravity: -110,
      colors: [GOLD, WHITE],
      glow: true,
      spread: 14,
    },
  ];
}

/** Life gained: the same rising shape as `motes`, in the gain green. */
export function heal(): EmitSpec[] {
  return [
    {
      shape: "mote",
      count: 14,
      speed: [40, 120],
      angle: UPWARD,
      ttl: [0.45, 0.9],
      size: [2, 5],
      drag: 0.55,
      gravity: -230,
      colors: [GREEN, WHITE],
      glow: true,
      spread: 12,
    },
  ];
}

/**
 * Name → recipe.
 *
 * `impact` is the one that takes an argument, so it is registered in its
 * radial form here and callers wanting a directed hit call `impact(angle)`
 * themselves. Keeping the map uniform is what lets a `TimedFx` name a preset
 * as a plain string.
 */
export const PRESETS: Record<PresetName, () => EmitSpec[]> = {
  impact: () => impact(null),
  explode,
  shatter,
  dissolve,
  dust,
  motes,
  heal,
};
