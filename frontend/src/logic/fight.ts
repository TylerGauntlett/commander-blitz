/**
 * What happens when two creatures fight.
 *
 * Blocking and attacking are the same arithmetic asked from opposite sides --
 * "does mine die, does theirs" -- and for two cycles only one side asked it.
 * `autoBlock.blockTier` read power and toughness and nothing else, so a
 * deathtouch blocker was ranked a chump against a 5/5 and a first striker was
 * scored as losing fights it walks away from (`docs/playtest-feedback-03.md`,
 * cycle 4 item 5). Putting the fight in one place is what stops the two
 * shortcuts from disagreeing about the same two cards.
 *
 * ## What is modelled, and what is not
 *
 * Deathtouch and first strike (and double strike, which is first strike for
 * this purpose) are here because they change *who dies*, which is the only
 * question these functions are asked. Trample, lifelink and menace are not:
 * trample changes what a chump block is *worth* rather than who dies, lifelink
 * changes a life total rather than a body, and menace changes how many blockers
 * are legal -- which the server already answers, in `blockableBy`. A shortcut
 * that guessed at any of them would be a shortcut the player has to check,
 * which is the whole cost it exists to save.
 *
 * Everything is derived from `CardView`, which already carries `keywords`,
 * `power`, `toughness` and `damage`. Nothing here decides what is LEGAL -- the
 * server's action list is the only thing that does.
 */

import type { CardView } from "../api/types";

/** Case-insensitive, because the engine's keyword casing is its own business. */
export function has(card: CardView, keyword: string): boolean {
  const wanted = keyword.toLowerCase();
  return card.keywords.some((entry) => entry.toLowerCase() === wanted);
}

/** Toughness left after damage already marked this turn. */
export function effectiveToughness(card: CardView): number {
  return (card.toughness ?? 0) - (card.damage ?? 0);
}

export function power(card: CardView): number {
  return card.power ?? 0;
}

/** Double strike is first strike, for the only question asked here. */
export function strikesFirst(card: CardView): boolean {
  return has(card, "first strike") || has(card, "double strike");
}

/**
 * Would `hitter`'s combat damage be lethal to `target`?
 *
 * Zero power never kills, deathtouch or not: no damage was dealt, and "any
 * nonzero amount is lethal" is a rule about damage that happened.
 */
export function wouldKill(hitter: CardView, target: CardView): boolean {
  const dealt = power(hitter);
  if (dealt <= 0) return false;
  if (has(hitter, "deathtouch")) return true;
  return dealt >= effectiveToughness(target);
}

/** Does `card` get to deal its damage before `foe` deals any? */
function preempts(card: CardView, foe: CardView): boolean {
  return strikesFirst(card) && !strikesFirst(foe);
}

/**
 * Does `card` come out of a fight with `foe` alive?
 *
 * A first striker that kills what it is fighting takes nothing back, which is
 * the case power-and-toughness alone gets wrong.
 */
export function survivesFight(card: CardView, foe: CardView): boolean {
  if (preempts(card, foe) && wouldKill(card, foe)) return true;
  return !wouldKill(foe, card);
}

/**
 * Does `card` actually kill `foe` in this fight?
 *
 * Not the same question as `wouldKill`: a creature killed by a first striker
 * never deals its damage, so it kills nothing however big it is.
 */
export function killsInFight(card: CardView, foe: CardView): boolean {
  if (!wouldKill(card, foe)) return false;
  if (preempts(foe, card) && wouldKill(foe, card)) return false;
  return true;
}

/** Keywords that get a creature past a ground blocker. */
const REACHES = new Set(["flying", "reach"]);

export function flies(card: CardView): boolean {
  return has(card, "flying");
}

/**
 * Could `blocker` legally be put in front of `attacker`?
 *
 * AN APPROXIMATION, AND ONLY EVER USED WHERE THE REAL ANSWER DOES NOT EXIST
 * YET. During a block declaration the server sends `add_blocker` actions and
 * `blockableBy` is the truth; during an ATTACK declaration nobody has asked the
 * question, so a client that wants to say "nothing they have can block this"
 * has to work it out. Flying against flying-or-reach is the case that decides
 * it almost every time; menace, protection and "can block only ..." are not
 * modelled, which is why this feeds a suggestion and never a rule.
 */
export function couldBlock(blocker: CardView, attacker: CardView): boolean {
  if (blocker.tapped) return false;
  if (!blocker.types.includes("Creature")) return false;
  if (!flies(attacker)) return true;
  return blocker.keywords.some((keyword) => REACHES.has(keyword.toLowerCase()));
}
