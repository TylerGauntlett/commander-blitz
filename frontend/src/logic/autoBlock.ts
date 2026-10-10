/**
 * Picking sensible blocks for the player.
 *
 * "All defend" is not "block everything": a bad block throws a creature away for
 * nothing. The ranking below is the one a player uses without thinking about it,
 * written down (playtest cycle 2, finding 7):
 *
 *   1. survive and kill   -- a free trade in your favour
 *   2. survive            -- a wall; you lose nothing
 *   3. die but kill       -- a real trade
 *   4. die for nothing    -- chump; only worth it under pressure
 *
 * This is a *suggestion*, and deliberately client-side. It stages, exactly as
 * clicking each creature does, so every pairing is visible and reversible before
 * anything is posted. It never invents a block: the pairs it chooses from come
 * from the server's legal-action list, so a menace attacker or an evasive one
 * simply has no candidates here.
 */

import type { CardView, GameView, LegalAction } from "../api/types";
import { blockableBy } from "./actionMatch";
import { killsInFight, survivesFight } from "./fight";
import { findCard } from "./zoneGrouping";

/** Lower is better. Mirrors the ranking above; 4 is a chump block. */
export type BlockTier = 1 | 2 | 3 | 4;

export interface BlockAssignment {
  blocker: number;
  attacker: number;
  tier: BlockTier;
}

/**
 * How good this block is, on the four-way ranking.
 *
 * The fight itself lives in `logic/fight.ts`, because attacking asks the same
 * two questions from the other side and the two shortcuts must not be allowed
 * to disagree about the same two cards. Deathtouch and first strike are
 * modelled there and change the answer here: a deathtouch blocker kills
 * whatever it stops, and a first striker survives fights it wins.
 *
 * Trample, lifelink and menace are still deliberately out -- see that file for
 * why. The button is a shortcut for a player who can see the same cards; it
 * does not have to be right, only reasonable and reversible.
 */
export function blockTier(blocker: CardView, attacker: CardView): BlockTier {
  const survives = survivesFight(blocker, attacker);
  const kills = killsInFight(blocker, attacker);
  if (survives && kills) return 1;
  if (survives) return 2;
  if (kills) return 3;
  return 4;
}

/**
 * A whole defence: one blocker per attacker, best pairings first.
 *
 * One blocker to one attacker, and one attacker to one blocker. Ganging up is
 * legal and sometimes right, but a default that quietly commits three creatures
 * to one attacker is a default that loses games -- and spreading the blocks is
 * what "pair cards" means. A player who wants a gang block clicks it.
 *
 * Chump blocks (tier 4) are excluded: giving a creature away for nothing is
 * never the *default* answer, only a decision a player makes when they are dying.
 * They remain one click away on the card itself.
 */
export function autoBlocks(state: GameView, actions: LegalAction[]): BlockAssignment[] {
  const blockers = [
    ...new Set(
      actions
        .filter((action) => action.kind === "add_blocker")
        .map((action) => action.source_oid),
    ),
  ].filter((oid): oid is number => oid !== null);

  const scored: BlockAssignment[] = [];
  for (const blocker of blockers) {
    const blockerCard = findCard(state, blocker);
    if (!blockerCard) continue;
    for (const attacker of blockableBy(actions, blocker)) {
      const attackerCard = findCard(state, attacker);
      if (!attackerCard) continue;
      scored.push({ blocker, attacker, tier: blockTier(blockerCard, attackerCard) });
    }
  }

  // Best pairings first; ties broken by oid so the same board always produces
  // the same defence. A suggestion that shuffled between renders would be
  // impossible to reason about.
  scored.sort((a, b) => a.tier - b.tier || a.attacker - b.attacker || a.blocker - b.blocker);

  const usedBlockers = new Set<number>();
  const blockedAttackers = new Set<number>();
  const chosen: BlockAssignment[] = [];
  for (const pair of scored) {
    if (pair.tier === 4) continue;
    if (usedBlockers.has(pair.blocker) || blockedAttackers.has(pair.attacker)) continue;
    usedBlockers.add(pair.blocker);
    blockedAttackers.add(pair.attacker);
    chosen.push(pair);
  }
  return chosen;
}
