/**
 * Splitting a battlefield into the lanes the board renders.
 *
 * Pure functions over the server's view, so they are cheap to unit test and the
 * components stay presentational.
 */

import type { CardView, GameView } from "../api/types";

export const LANES = ["Lands", "Creatures", "Artifacts & Enchantments", "Other"] as const;
export type Lane = (typeof LANES)[number];

/** Which lane a permanent belongs in. Creature beats land for a creature-land. */
export function laneFor(card: CardView): Lane {
  if (card.types.includes("Creature")) return "Creatures";
  if (card.types.includes("Land")) return "Lands";
  if (card.types.includes("Artifact") || card.types.includes("Enchantment")) {
    return "Artifacts & Enchantments";
  }
  return "Other";
}

export type LaneMap = Record<Lane, CardView[]>;

export function emptyLanes(): LaneMap {
  return {
    Lands: [],
    Creatures: [],
    "Artifacts & Enchantments": [],
    Other: [],
  };
}

/** Group one player's permanents into lanes, preserving battlefield order. */
export function groupBattlefield(state: GameView, pid: number): LaneMap {
  const lanes = emptyLanes();
  for (const card of state.battlefield) {
    if (card.controller !== pid) continue;
    lanes[laneFor(card)].push(card);
  }
  return lanes;
}

/** Seats in display order: the viewer last (bottom of the screen), then clockwise. */
export function seatOrder(state: GameView): number[] {
  const count = state.players.length;
  const others: number[] = [];
  for (let i = 1; i < count; i += 1) {
    others.push((state.seat + i) % count);
  }
  return [...others, state.seat];
}

export function playerOf(state: GameView, pid: number) {
  return state.players[pid];
}

/** A short label for the card tile: "2/2", or "" for a non-creature. */
export function statLine(card: CardView): string {
  if (card.power === null || card.toughness === null) return "";
  if (card.zone !== "battlefield") return `${card.power}/${card.toughness}`;
  const remaining = card.toughness - (card.damage ?? 0);
  return `${card.power}/${remaining}`;
}

/** Counters rendered as short badges, e.g. ["+1/+1 x3"]. */
export function counterBadges(card: CardView): string[] {
  const counters = card.counters ?? {};
  return Object.entries(counters)
    .filter(([, amount]) => amount > 0)
    .map(([kind, amount]) => (amount === 1 ? kind : `${kind} x${amount}`));
}

export interface ManaPip {
  symbol: string;
  /** Stable within a cost: "{G}{G}" repeats a symbol, so position disambiguates. */
  key: string;
}

/** Mana symbols split for pip rendering: "{4}{G}{U}" -> 4, G, U. */
export function manaPips(manaCost: string): ManaPip[] {
  if (!manaCost || manaCost === "{0}") return [];
  return [...manaCost.matchAll(/\{([^}]*)\}/g)].map((match, index) => ({
    symbol: match[1],
    key: `${index}-${match[1]}`,
  }));
}
