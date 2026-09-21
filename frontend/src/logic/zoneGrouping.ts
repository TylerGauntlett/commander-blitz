/**
 * Splitting a battlefield into the lanes the board renders.
 *
 * Pure functions over the server's view, so they are cheap to unit test and the
 * components stay presentational. Card *appearance* lives in `cardStyle.ts`;
 * this module is only about where a card goes.
 */

import type { CardView, GameView, PlayerView } from "../api/types";

/**
 * The lanes, declared front to back -- the order they render for the viewer,
 * nearest the opponent first.
 *
 * A player's lands go in the row closest to them, which is how the game is
 * physically played and the opposite of the order this used to declare. The two
 * front lanes share one band; lands own the band behind them. See `PlayerMat`.
 *
 * These strings are identity, not copy: `Lane` derives `data-dropzone` and
 * `data-testid` from them, and several e2e specs select on `lane-0-Lands`. What
 * the player reads comes from `LANE_LABELS`.
 */
export const LANES = ["Creatures", "Artifacts & Enchantments", "Lands"] as const;
export type Lane = (typeof LANES)[number];

export const LANE_LABELS: Record<Lane, string> = {
  Creatures: "Creatures",
  "Artifacts & Enchantments": "Global Artifacts & Enchantments",
  Lands: "Lands",
};

/**
 * Which lane a permanent belongs in.
 *
 * Creature beats land, so a creature-land is where its body can be blocked
 * rather than where it taps -- the same call `laneFor` has always made.
 *
 * Battles ride with them for exactly that reason -- 506.2 makes a battle the
 * third thing an attack can be declared against, so a battle parked in the
 * artifacts row would be a defender you cannot aim at.
 *
 * Planeswalkers ride with the creatures: they are what combat is pointed at, so
 * they belong on the line combat is declared across, not in a leftover row.
 *
 * The two attachment clauses answer different questions. On the battlefield an
 * Aura or Equipment is placed by `attached_to`, because it is drawn tucked
 * behind its host. From *hand* nothing is attached yet, and `canDropOnLane` asks
 * this same function which lane to highlight for a drag -- the subtype clause is
 * what makes an Aura light up the band it is actually heading for.
 */
export function laneFor(card: CardView): Lane {
  if (card.attached_to != null) return "Creatures";
  if (card.types.includes("Creature")) return "Creatures";
  if (card.types.includes("Planeswalker")) return "Creatures";
  if (card.types.includes("Battle")) return "Creatures";
  if (card.types.includes("Land")) return "Lands";
  if (card.subtypes.includes("Aura") || card.subtypes.includes("Equipment")) return "Creatures";
  return "Artifacts & Enchantments";
}

export type LaneMap = Record<Lane, CardView[]>;

export function emptyLanes(): LaneMap {
  return {
    Creatures: [],
    "Artifacts & Enchantments": [],
    Lands: [],
  };
}

/**
 * Is this card drawn tucked behind a host on the same mat?
 *
 * Only then is it held out of the lanes. An Aura you control on an *opponent's*
 * creature has a host, but not one on this mat, so it stays a loose card in its
 * own lane -- a permanent that belongs to nobody's mat would simply vanish.
 */
function tuckedHost(card: CardView, byOid: Map<number, CardView>): CardView | null {
  if (card.attached_to == null) return null;
  const host = byOid.get(card.attached_to);
  if (!host || host.controller !== card.controller) return null;
  return host;
}

function battlefieldIndex(state: GameView): Map<number, CardView> {
  const byOid = new Map<number, CardView>();
  for (const card of state.battlefield) byOid.set(card.oid, card);
  return byOid;
}

/**
 * Group one player's permanents into lanes, preserving battlefield order.
 *
 * Permanents drawn tucked behind a host are left out; `attachmentsFor` returns
 * them keyed by the host that carries them.
 */
export function groupBattlefield(state: GameView, pid: number): LaneMap {
  const lanes = emptyLanes();
  const byOid = battlefieldIndex(state);
  for (const card of state.battlefield) {
    if (card.controller !== pid) continue;
    if (tuckedHost(card, byOid)) continue;
    lanes[laneFor(card)].push(card);
  }
  return lanes;
}

/** Host oid -> the permanents drawn tucked behind it, in battlefield order. */
export function attachmentsFor(state: GameView, pid: number): Map<number, CardView[]> {
  const byOid = battlefieldIndex(state);
  const tucked = new Map<number, CardView[]>();
  for (const card of state.battlefield) {
    if (card.controller !== pid) continue;
    const host = tuckedHost(card, byOid);
    if (!host) continue;
    const existing = tucked.get(host.oid);
    if (existing) existing.push(card);
    else tucked.set(host.oid, [card]);
  }
  return tucked;
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
 * How many commanders are sitting in a player's command zone.
 *
 * Not `player.command.length`: the command zone also holds emblems (114), and
 * the seat's and orb's command pile is the commander's count -- an Ob Nixilis
 * emblem must not read as a second commander waiting to be cast.
 */
export function commandZoneCommanderCount(player: PlayerView): number {
  return player.command.filter((card) => card.is_commander).length;
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
  // The command zone also holds emblems (114), which are neither commanders
  // nor castable, and must not take the plinth or the seat's art.
  const found: CardView[] = player.command.filter((card) => card.is_commander);
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

/**
 * The card behind an oid, wherever the viewer can currently see it.
 *
 * The stack is searched first, and it is not an edge case: `commandersOf` above
 * deliberately keeps a commander on the plinth while it is mid-cast, so between
 * the click and the spell resolving the panel is showing a card that lives in no
 * other zone. Without this pass the preview rail blanks to "Hover a card to read
 * it" for exactly the beat the player is watching. `findCardByDefId` has
 * searched the stack first for the same reason since it was written.
 */
export function findCard(state: GameView, oid: number): CardView | null {
  for (const item of state.stack) {
    if (item.card?.oid === oid) return item.card;
  }
  for (const card of state.battlefield) {
    if (card.oid === oid) return card;
  }
  for (const player of state.players) {
    // `library_top` is a zone of one: revealed ("play with the top card of your
    // library revealed") or looked at ("you may look at the top card of your
    // library any time") is the only way a library card is visible, and it has
    // to be searched here or the preview rail blanks on the one card the whole
    // mechanic exists to show. Whichever put it there, this seat was sent it,
    // so hovering it is allowed.
    if (player.library_top?.oid === oid) return player.library_top;
    for (const zone of [player.hand ?? [], player.graveyard, player.exile, player.command]) {
      for (const card of zone) {
        if (card.oid === oid) return card;
      }
    }
  }
  return null;
}
