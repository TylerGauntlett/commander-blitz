/**
 * Splitting a battlefield into the lanes the board renders.
 *
 * Pure functions over the server's view, so they are cheap to unit test and the
 * components stay presentational. Card *appearance* lives in `cardStyle.ts`;
 * this module is only about where a card goes.
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

/**
 * Find a card anywhere the viewer can see it.
 *
 * Decision options and action targets are bare oids, so every dialog that wants
 * to draw the thing being chosen has to resolve one. Battlefield first, since
 * that is where targets almost always are.
 */
export function findCard(state: GameView, oid: number): CardView | null {
  for (const card of state.battlefield) {
    if (card.oid === oid) return card;
  }
  for (const player of state.players) {
    for (const zone of [player.hand ?? [], player.graveyard, player.exile, player.command]) {
      for (const card of zone) {
        if (card.oid === oid) return card;
      }
    }
  }
  return null;
}
