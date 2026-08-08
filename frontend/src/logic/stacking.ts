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
  /**
   * Permanents drawn tucked behind `top`: its auras and equipment.
   *
   * Always empty unless the group is a host, and a host is always a group of
   * one -- see `stackCards`.
   */
  attachments: CardView[];
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
 * `attachments` maps a host oid to the permanents drawn tucked behind it (see
 * `attachmentsFor`). A host never merges with anything: `stackKey` describes a
 * card, not what is hanging off it, so an enchanted Grizzly Bears would
 * otherwise hide behind an identical bare one and take the aura with it. Giving
 * every host a key of its own follows this module's rule -- splitting stacks is
 * always safe, hiding board state never is -- and it is what makes a group's
 * `attachments` unambiguously belong to its `top`.
 */
export function stackCards(
  cards: CardView[],
  attachments?: ReadonlyMap<number, CardView[]>,
): CardStackGroup[] {
  const groups = new Map<string, CardView[]>();
  const order: string[] = [];

  for (const card of cards) {
    const key = attachments?.has(card.oid) ? `host/${card.oid}` : stackKey(card);
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
    return {
      key,
      cards: members,
      top: members[0],
      count: members.length,
      attachments: attachments?.get(members[0].oid) ?? [],
    };
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
  // A host is always a group of one, so `group.count > 1` guarantees there is
  // nothing attached here to hand on to either half.
  return [
    { key: `${group.key}#on`, cards: hits, top: hits[0], count: hits.length, attachments: [] },
    { key: `${group.key}#off`, cards: rest, top: rest[0], count: rest.length, attachments: [] },
  ];
}
