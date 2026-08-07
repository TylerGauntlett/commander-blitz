/**
 * Collapsing identical permanents into one stack.
 *
 * A Commander board is wide -- twelve basics and a pile of tokens push the
 * interesting permanents off screen. Stacking buys that space back.
 *
 * The rule that matters: two cards may only merge when they are
 * *interchangeable*, because a stack hides its members. Anything that changes
 * how a permanent behaves or what the player should be worried about is part of
 * the key, so an untapped Forest never hides behind a tapped one and a creature
 * with a +1/+1 counter never hides behind one without.
 */

import type { CardView } from "../api/types";

export interface CardStackGroup {
  /** Stable identity for React and for `layoutId`. */
  key: string;
  /** Every card in the group, in battlefield order. */
  cards: CardView[];
  /** The card whose face is drawn; the one a click acts on by default. */
  top: CardView;
  count: number;
}

/** Counters as a stable string: "+1/+1:2|charge:1". */
function counterSignature(card: CardView): string {
  const counters = card.counters ?? {};
  const entries = Object.entries(counters).filter(([, amount]) => amount !== 0);
  if (entries.length === 0) return "";
  entries.sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return entries.map(([kind, amount]) => `${kind}:${amount}`).join("|");
}

/**
 * The identity two cards must share to be stacked.
 *
 * Deliberately conservative. Adding a field here can only split stacks, which
 * is safe; leaving one out hides board state, which is not.
 */
export function stackKey(card: CardView): string {
  return [
    card.card_id,
    card.controller,
    card.tapped ? "T" : "-",
    card.summoning_sick ? "S" : "-",
    card.damage ?? 0,
    counterSignature(card),
    card.attacking ? "A" : "-",
    card.blocking ? "B" : "-",
    card.attached_to ?? "-",
    card.is_commander ? "C" : "-",
    card.is_token ? "K" : "-",
  ].join("/");
}

/**
 * Group cards into stacks, preserving first-appearance order.
 *
 * Attached permanents (auras, equipment) are never stacked away from their
 * host, and anything a stack would hide is split out by `stackKey`.
 */
export function stackCards(cards: CardView[]): CardStackGroup[] {
  const groups = new Map<string, CardView[]>();
  const order: string[] = [];

  for (const card of cards) {
    const key = stackKey(card);
    const existing = groups.get(key);
    if (existing) {
      existing.push(card);
    } else {
      groups.set(key, [card]);
      order.push(key);
    }
  }

  return order.map((key) => {
    const members = groups.get(key) as CardView[];
    return { key, cards: members, top: members[0], count: members.length };
  });
}

/**
 * Cards that must stay individually visible because a legal action names them.
 *
 * Stacking is cosmetic, but it must never bury a choice: if three of five
 * Forests can still be tapped for mana, the player has to be able to reach
 * them. Splitting the actionable ones out keeps every legal action clickable.
 */
export function splitActionable(
  group: CardStackGroup,
  actionableOids: ReadonlySet<number>,
): CardStackGroup[] {
  if (group.count === 1) return [group];
  const hits = group.cards.filter((card) => actionableOids.has(card.oid));
  if (hits.length === 0 || hits.length === group.count) return [group];

  const rest = group.cards.filter((card) => !actionableOids.has(card.oid));
  return [
    { key: `${group.key}#on`, cards: hits, top: hits[0], count: hits.length },
    { key: `${group.key}#off`, cards: rest, top: rest[0], count: rest.length },
  ];
}
