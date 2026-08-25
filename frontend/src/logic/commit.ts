/**
 * What the turn is waiting on you to press, wherever the ring happens to be.
 *
 * Every decision this game asks ends at ONE control in the commit dock: Pass on
 * a priority window, All attack then Attack on a declaration, All defend then
 * Block, and "No attacks" when nothing can go. The dock lives in the right rail
 * and the ring is almost never near it -- you are in your hand, or out on your
 * own board choosing what to swing -- so `L2` exists to jump there and `A`
 * presses it. Two presses, every phase, thirteen phases a turn.
 *
 * `X` collapses that to one. It is the contextual secondary and it is empty on
 * most stops, so it takes the job where it has nothing else to do: a card with
 * an ability keeps `Activate`, a staged attacker keeps `Re-aim`, and everywhere
 * else `X` is "get on with it".
 *
 * ## Why this is its own module
 *
 * Because two things need the answer and they must not be allowed to differ.
 * `Table.secondary` presses it; `logic/verbs.ts` prints its name in the hint
 * bar. `verbs.ts`'s header is emphatic that a bar promising a verb the button
 * does not have is worse than no bar -- and it keeps that promise by RESTATING
 * the routing branch for branch, checked by a test. That works and it is a
 * discipline; one shared function is a guarantee. Everything else about `X` is
 * still mirrored the old way, because the contextual branches are about the
 * board and belong with the board.
 *
 * ## Staging, and the two that are real actions
 *
 * "All attack" and the Attack slab are LOCAL: they write to `uiStore` and the
 * slab declares whatever is staged, so neither exists in the action list and
 * neither has an id to post. Those two are pressed by clicking the control the
 * panel already rendered -- the same discipline `useCursorNav` uses for `A`,
 * which is what stops a controller ever reaching an action a pointer cannot.
 * "No attacks" and Pass are server actions and carry ids, so those are posted
 * directly and this says which.
 */

import type { GameView, LegalAction } from "../api/types";
import { availableAttackers, availableBlockers } from "./actionMatch";
import { autoBlocks } from "./autoBlock";
import type { Staging } from "./verbs";

export interface Commitment {
  /**
   * Which control in the dock this is.
   *
   * `all` and `confirm` are `data-testid`s on controls the panel renders;
   * `skip` and `pass` are server actions and come with an `actionId`.
   */
  target: "all" | "confirm" | "skip" | "pass";
  /** The verb, in the button's own words. A bar that renames a button lies. */
  verb: string;
  /** The action to post, for the two that are real actions. Null for staging. */
  actionId: string | null;
}

/**
 * The one control the decision in front of the player ends at, or `null` when
 * pressing anything would be a guess.
 *
 * ## The order, which is the whole rule
 *
 * **Something staged wins.** Once a creature is aimed, the thing you want is to
 * send it -- and a second `X` that re-staged instead would be a button whose
 * meaning depends on how many times you have pressed it.
 *
 * **Nothing staged goes to the "all" mark**, which STAGES and does not submit.
 * That is what makes this safe to put on a hotkey: the first press is always
 * reversible, and the second one is the one that commits, by which time the bar
 * has changed from `All attack` to `Attack` and said so.
 *
 * **Nothing declarable at all goes to the decline**, and only then. When no
 * creature can attack, the panel promotes "No attacks" to the whole bar because
 * declining IS the decision -- there is nothing else on screen to press, so
 * offering it costs the player nothing they could have chosen instead.
 *
 * **A defence worth nothing offers nothing.** "All defend" declines a chump
 * block, so on a board where every block throws a creature away the mark is
 * disabled -- and `X` goes quiet rather than reaching past it to "No blocks".
 * Taking the damage is a decision a player makes, not a default: they still
 * have every card on the board, and the panel still has the row.
 */
export function commitmentFor(
  state: GameView,
  actions: LegalAction[],
  staging: Staging,
): Commitment | null {
  /*
   * NOTHING WHILE A SPELL IS WAITING FOR A TARGET.
   *
   * Mid-selection the decision in front of the player is "point at something",
   * and `act()` calls `endTargeting()` on its way out -- so an `X` that fell
   * through to Pass here would abandon a half-cast spell AND give up priority,
   * from a button whose whole promise is that it presses the obvious thing. `B`
   * is how you back out of a selection, and it says so in the bar.
   */
  if (staging.targeting) return null;

  const decision = state.pending?.player === state.seat ? state.pending.kind : null;
  const decline = () => actions.find((action) => action.kind === "finish_declaration") ?? null;

  if (decision === "declare_attackers") {
    if (Object.keys(staging.stagedAttacks).length > 0) {
      return { target: "confirm", verb: "Attack", actionId: null };
    }
    if (availableAttackers(actions).length > 0) {
      return { target: "all", verb: "All attack", actionId: null };
    }
    const finish = decline();
    return finish ? { target: "skip", verb: "No attacks", actionId: finish.id } : null;
  }

  if (decision === "declare_blockers") {
    if (Object.keys(staging.stagedBlocks).length > 0) {
      return { target: "confirm", verb: "Block", actionId: null };
    }
    if (availableBlockers(actions).length === 0) {
      const finish = decline();
      return finish ? { target: "skip", verb: "No blocks", actionId: finish.id } : null;
    }
    /*
     * The same filter the mark's own `disabled` uses, and it has to be: a bar
     * that says `X All defend` over a mark nothing happens on is the defect
     * `verbs.ts` exists to prevent, arriving through a second derivation of one
     * fact rather than through a second copy of a string.
     */
    const worth = autoBlocks(state, actions).filter(
      ({ blocker }) => staging.stagedBlocks[blocker] === undefined,
    );
    return worth.length > 0 ? { target: "all", verb: "All defend", actionId: null } : null;
  }

  const pass = actions.find((action) => action.kind === "pass");
  return pass ? { target: "pass", verb: "Pass", actionId: pass.id } : null;
}

/** The `data-testid` of the control to press, for the two that are local staging. */
export const COMMIT_TESTID: Record<Commitment["target"], string> = {
  all: "combat-all",
  confirm: "combat-confirm",
  skip: "combat-skip",
  pass: "commit",
};
