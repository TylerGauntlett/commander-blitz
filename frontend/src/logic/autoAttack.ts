/**
 * Picking a sensible attack for the player.
 *
 * The mirror of `autoBlock.ts`, and it exists because the two halves of combat
 * had different shortcuts. "All defend" has been ranked since cycle 2 -- it
 * declines a chump block, because giving a creature away for nothing is never
 * the *default* answer. "All attack" staged every legal attacker, so the
 * shortcut for the more consequential decision of the turn was the one you had
 * to undo card by card: a 0/1 Blood Artist swung into an untapped 1/1 and the
 * board you needed at home was tapped out.
 *
 * The ranking is the one a player uses without thinking about it:
 *
 *   1. unopposed  -- nothing they have untapped can block it
 *   2. safe       -- it walks away from every block they could make
 *   3. trades     -- it can die, but never for nothing
 *   4. dies       -- some block kills it and survives; held back
 *   5. needed     -- safe to send, but they can kill you on the swing back
 *
 * Tiers 1-3 are what the first press stages. A SECOND press stages the rest,
 * which is the alpha strike -- the case where the ranking is wrong on purpose
 * because you are racing, and no amount of arithmetic here should be allowed to
 * make that two dozen presses.
 *
 * This is a *suggestion*, and deliberately client-side. It stages, exactly as
 * pressing each creature does, so every pairing is visible and reversible
 * before anything is posted. It never invents an attack: the pairs come from
 * the server's `add_attacker` list, so a creature that cannot attack simply has
 * no candidates here.
 *
 * ## Why the blockers are guessed, and the blocks are not
 *
 * During a BLOCK declaration the server has already enumerated who may block
 * what, and `blockableBy` is the truth. During an ATTACK declaration nobody has
 * asked, so "can anything they have stop this" has to be worked out from the
 * two boards -- `fight.couldBlock`, which models flying against flying-or-reach
 * and nothing else. That is why the tiers here are softer than `blockTier`'s,
 * and why tier 4 is `held back` rather than `never`.
 */

import type { CardView, GameView, LegalAction } from "../api/types";
import { defendersFor } from "./actionMatch";
import { couldBlock, killsInFight, survivesFight } from "./fight";
import { findCard, groupBattlefield } from "./zoneGrouping";

/** Lower is better. Mirrors the ranking above; 4 and 5 are held back. */
export type AttackTier = 1 | 2 | 3 | 4 | 5;

export interface AttackAssignment {
  attacker: number;
  defender: number;
  tier: AttackTier;
}

/** The tiers the first press stages. */
export const SENT: ReadonlySet<AttackTier> = new Set<AttackTier>([1, 2, 3]);

/** Every untapped creature `pid` has that could be put in front of something. */
function guardsOf(state: GameView, pid: number): CardView[] {
  return groupBattlefield(state, pid).Creatures.filter(
    (card) => card.types.includes("Creature") && !card.tapped,
  );
}

/**
 * How good this attack is, ignoring what else you are sending.
 *
 * The defender picks the block, so the attacker is only as safe as their BEST
 * answer to it: it is safe when it survives every block, and it trades when
 * every block that kills it dies for the trouble.
 */
export function attackTier(attacker: CardView, guards: readonly CardView[]): AttackTier {
  const answers = guards.filter((guard) => couldBlock(guard, attacker));
  if (answers.length === 0) return 1;
  if (answers.every((guard) => survivesFight(attacker, guard))) return 2;
  const lethal = answers.filter((guard) => !survivesFight(attacker, guard));
  if (lethal.every((guard) => killsInFight(attacker, guard))) return 3;
  return 4;
}

/**
 * A whole attack: one defender per attacker, best first.
 *
 * `defendersFor(actions, oid)[0]` is the aim, which is exactly what pressing
 * the creature already does -- in a pod `X` re-aims and the panel's chips name
 * every seat, so choosing a seat is not this function's business. What it
 * decides is WHO SWINGS.
 *
 * ## The one rule that looks at the whole board rather than one creature
 *
 * A creature that is safe attacking is usually the creature that is useful
 * blocking, and those are the same turn. So when an opponent's board could
 * simply kill you on the swing back -- their total creature power is at least
 * your life -- only the unopposed attackers go: they cannot be blocked, so
 * sending them costs nothing you could have used at home. That is tier 5, and
 * it is a property of the position rather than of the card, which is why it is
 * applied here and not in `attackTier`.
 *
 * Ties break by oid, so the same board always produces the same attack. A
 * suggestion that shuffled between renders would be impossible to reason about.
 */
export function autoAttacks(state: GameView, actions: LegalAction[]): AttackAssignment[] {
  const attackers = [
    ...new Set(
      actions
        .filter((action) => action.kind === "add_attacker")
        .map((action) => action.source_oid),
    ),
  ].filter((oid): oid is number => oid !== null);

  const guards = new Map<number, CardView[]>();
  const out: AttackAssignment[] = [];
  for (const attacker of attackers) {
    const card = findCard(state, attacker);
    if (!card) continue;
    const [defender] = defendersFor(actions, attacker);
    if (defender === undefined) continue;
    if (!guards.has(defender)) guards.set(defender, guardsOf(state, defender));
    let tier = attackTier(card, guards.get(defender) ?? []);
    if (tier !== 1 && wouldDieAtHome(state, defender)) tier = 5;
    out.push({ attacker, defender, tier });
  }
  out.sort((a, b) => a.tier - b.tier || a.attacker - b.attacker);
  return out;
}

/**
 * Could that seat's board kill you on the swing back?
 *
 * Total power against your life, and no cleverer than that on purpose. It is
 * the number a player glances at, it is already on the seat strip as part of
 * `threatOf`, and a forecast the client cannot verify is worse than a rule of
 * thumb it can state.
 */
function wouldDieAtHome(state: GameView, defender: number): boolean {
  const you = state.players[state.seat];
  if (!you) return false;
  let power = 0;
  for (const card of groupBattlefield(state, defender).Creatures) {
    if (card.types.includes("Creature")) power += card.power ?? 0;
  }
  return power >= you.life;
}

/** The pairs the first press stages: everything worth sending. */
export function sensibleAttacks(state: GameView, actions: LegalAction[]): AttackAssignment[] {
  return autoAttacks(state, actions).filter((pair) => SENT.has(pair.tier));
}
