/**
 * Where the ring should be when the game asks you something.
 *
 * A pointer arrives at a decision already near it, because you moved it there.
 * A ring is wherever it was left, and on a 1280x800 board that can be four
 * regions away from the thing the turn is now waiting on -- so the step that
 * changes what is being asked is the moment to move it.
 *
 * ## Pure, and driven from a narrow effect
 *
 * Nothing here touches the DOM or the cursor: it answers "which region does
 * this decision live in" and `Table` does the moving. That is what makes it
 * testable as a table of states, and it is also the honest boundary -- the rule
 * is about the GAME, and where a region happens to be drawn is not.
 *
 * ## It must not fight the player
 *
 * `Table` keys the effect on `state.pending?.kind` and `state.step` only. Run on
 * every render it would drag the ring back every time the engine pushed a state
 * -- which on a four-seat pod is several times a second while the AI plays --
 * and a ring that returns to where the app thinks you should be is worse than
 * one that stays where you put it.
 *
 * A modal decision returns `null`, and that is not "no opinion": the dialog
 * traps the ring itself (`stopRoot`), so moving it first would put it somewhere
 * the trap is about to take it away from.
 */

import type { GameView, LegalAction } from "../api/types";
import type { GroupId } from "../input/groups";

/**
 * Steps where the decision is about creatures, and the creatures are on the
 * board rather than in a list.
 *
 * Combat is staged by pressing the permanents -- `Table.onBoardCard` routes an
 * attacker toggle and a blocker pairing -- so the board is where a player's
 * hands should already be. The panel carries the same choices as rows, which is
 * why this is a nudge rather than a rule about where the game can be played.
 */
const COMBAT = new Set(["declare_attackers", "declare_blockers"]);

/**
 * Which region the decision in front of the player lives in.
 *
 * `null` means "leave the ring alone" -- either nothing is being asked of this
 * seat, or something else already owns where the ring goes.
 *
 * `boardCanDecide` is the one thing here the game cannot answer, and it is why
 * this takes an argument rather than a second `COMBAT` set. A block declaration
 * is made by pressing your creature and then the attacker it stops -- and at
 * 1280x800 an opponent's lanes are clipped to zero height, so the attacker is
 * not a stop the ring can land on. Sent to the board there, the ring arrived
 * somewhere with exactly half a decision in it: pressing your own creature
 * answered nothing and every direction out of it was a wall or a seat. `Table`
 * asks the DOM whether any attacker is landable and passes the answer, because
 * "which region does this decision live in" and "is that region drawn right
 * now" are different questions and only the first one is about the game.
 */
export function groupForDecision(
  state: GameView,
  actions: LegalAction[],
  isModal: boolean,
  boardCanDecide = true,
): GroupId | null {
  // Not your decision. The AI is thinking, or another human is.
  if (state.pending && state.pending.player !== state.seat) return null;
  // Somebody else's priority window is not a prompt to move for either.
  if (state.priority_player !== null && state.priority_player !== state.seat) return null;

  // A dialog traps the ring on its own; moving it first is moving it twice.
  if (isModal) return null;

  const kind = state.pending?.player === state.seat ? state.pending.kind : null;
  if (kind && COMBAT.has(kind)) return boardCanDecide ? "board" : "acts";

  /*
   * Somebody else's spell or ability is waiting on you: the stack, so the card
   * is being read before anything is decided about it. The engine stops for an
   * opponent's removal even when Pass is all you have (`_faces_disruption`),
   * and that stop is only worth its press if the card is in front of you;
   * with an answer in hand, reading what you are answering is the decision.
   */
  if (opponentTop(state) !== null) return "stack";

  /*
   * Your main phase, with something castable in hand.
   *
   * The hand rather than the panel, because a main phase is spent deciding WHAT
   * to play and the panel's rows are one line each while the hand is the cards.
   * Guarded on there actually being a play available: an empty hand, or a hand
   * of things you cannot afford, would send the ring somewhere with nothing to
   * do -- and `groupsPresent` would then decline to go there anyway, which
   * would look like the button not working.
   */
  const main = state.phase === "precombat_main" || state.phase === "postcombat_main";
  if (main && state.active_player === state.seat) {
    const canPlay = actions.some(
      (action) => action.kind === "cast" || action.kind === "play_land",
    );
    if (canPlay) return "hand";
  }

  /*
   * Otherwise the panel, which is where every decision has a row.
   *
   * Only when there is more than one thing to say, though. A step whose only
   * legal action is passing does not deserve the ring being taken off whatever
   * the player was reading -- that is the AI's turn, and reading is what a
   * player does during it.
   */
  return actions.length > 1 ? "acts" : null;
}

/**
 * The newest item on the stack that somebody else put there, while the
 * viewer holds priority over it -- else null.
 *
 * The newest of THEIRS, not the top: answering it puts your own spell on top,
 * and that must not read as a new decision and drag the ring off the card it
 * just pressed. `useTableRegions` keys its nudge on this, so a fresh threat is
 * a fresh nudge and a response to it is not.
 */
export function opponentTop(state: GameView): number | null {
  if (state.priority_player !== state.seat) return null;
  if (state.pending && state.pending.player !== state.seat) return null;
  let newest: number | null = null;
  for (const item of state.stack) {
    if (item.controller !== state.seat) newest = item.sid;
  }
  return newest;
}
