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
/**
 * A player's commanders and where each one currently is.
 *
 * The dock shows the commander *at all times*, not only while it sits in the
 * command zone -- in Commander it is the card the whole deck is about, and
 * having it vanish from the interface the moment it resolves is the opposite of
 * what a player wants to track. So this searches the visible zones in the order
 * a commander travels: command, battlefield, then the places it can be exiled
 * or killed to before it is put back.
 *
 * The stack is searched too, and it is not an edge case: casting a commander is
 * the whole point of the dock, and between the click and the spell resolving the
 * card is in no other zone. Without it the dock blinks empty at exactly the
 * moment the player is watching it.
 *
 * A commander in a *hidden* zone (hand or library, after a return-to-hand) has
 * no view to return, and is simply absent until it reappears.
 */
export function commandersOf(state: GameView, pid: number): CardView[] {
  const player = state.players[pid];
  const found: CardView[] = [...player.command];
  const seen = new Set(found.map((card) => card.oid));

  const consider = (card: CardView | null) => {
    if (!card || !card.is_commander || card.owner !== pid || seen.has(card.oid)) return;
    seen.add(card.oid);
    found.push(card);
  };
  for (const item of state.stack) consider(item.card);
  for (const card of state.battlefield) consider(card);
  for (const card of player.graveyard) consider(card);
  for (const card of player.exile) consider(card);
  return found;
}

/**
 * Find any copy of a printed card the viewer can currently see.
 *
 * Events name a card by its *definition* id ("sol_ring"), not by object id, so
 * the spotlight cannot resolve a face the way a target can. This searches in the
 * order a spotlit card is likely to be: still on the stack if narration has
 * caught up, otherwise wherever it landed once it resolved.
 *
 * `controller` narrows it when two players run the same card, which in a format
 * of singleton decks is common enough to matter and cheap enough to handle.
 * Falls back to any copy, since showing the right card belonging to the wrong
 * player still shows the right card.
 */
export function findCardByDefId(
  state: GameView,
  cardId: string,
  controller?: number,
): CardView | null {
  let fallback: CardView | null = null;
  const consider = (card: CardView | null): CardView | null => {
    if (!card || card.card_id !== cardId) return null;
    if (controller === undefined || card.controller === controller) return card;
    fallback ??= card;
    return null;
  };

  for (const item of state.stack) {
    const hit = consider(item.card);
    if (hit) return hit;
  }
  for (const card of state.battlefield) {
    const hit = consider(card);
    if (hit) return hit;
  }
  for (const player of state.players) {
    for (const zone of [player.graveyard, player.exile, player.command, player.hand ?? []]) {
      for (const card of zone) {
        const hit = consider(card);
        if (hit) return hit;
      }
    }
  }
  return fallback;
}

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
