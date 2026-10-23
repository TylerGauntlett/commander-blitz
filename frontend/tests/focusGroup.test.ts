/**
 * Where the ring goes when the game asks you something.
 *
 * A table of states, because that is what the rule is. The cases worth pinning
 * are all the ones where the answer is **leave it alone** -- a rule that moves
 * the ring too eagerly is worse than no rule, because it takes the board away
 * from a player who was reading it.
 */

import { describe, expect, it } from "vitest";
import type { GameView, LegalAction } from "../src/api/types";
import { groupForDecision, opponentTop } from "../src/logic/focusGroup";
import { chooseTarget } from "../src/testing/scenarios";
import { action, gameView, pending, player, stackItem } from "./fixtures";

function view(overrides: Partial<GameView> = {}): GameView {
  return gameView({
    seat: 0,
    active_player: 0,
    priority_player: 0,
    phase: "precombat_main",
    players: [player({ pid: 0 }), player({ pid: 1 })],
    ...overrides,
  });
}

const cast: LegalAction = action({ id: "a1", kind: "cast" });
const pass: LegalAction = action({ id: "a0", kind: "pass" });

describe("combat", () => {
  it("sends the ring to the board to declare attackers", () => {
    /*
     * Combat is staged by pressing the PERMANENTS -- `Table.onBoardCard` routes
     * an attacker toggle and a blocker pairing -- so the board is where a
     * player's hands should already be. The panel carries the same choices as
     * rows, which is why this is a nudge rather than a claim about where the
     * game can be played.
     */
    const state = view({
      phase: "combat",
      pending: pending({ kind: "declare_attackers", player: 0 }),
    });
    expect(groupForDecision(state, [cast, pass], false)).toBe("board");
  });

  it("does the same for blockers", () => {
    const state = view({
      phase: "combat",
      active_player: 1,
      pending: pending({ kind: "declare_blockers", player: 0 }),
    });
    expect(groupForDecision(state, [cast, pass], false)).toBe("board");
  });

  /*
   * THE BOARD HELD HALF A DECISION, AND THE RING WAS SENT TO IT ANYWAY.
   *
   * A block is your creature and then the attacker it stops. At 1280x800 an
   * opponent's lanes are clipped to zero height, so `stops.ts:onScreen` refuses
   * to land the ring on an attacker -- correctly. Sent to the board there, `A`
   * on your own creature answered nothing and every direction out of it was a
   * wall or a seat, while the panel had carried the whole pairing as rows the
   * entire time. `Table.boardCanDecide` asks the DOM; this is the rule it feeds.
   */
  it("sends blockers to the panel when no attacker can be landed on", () => {
    const state = view({
      phase: "combat",
      active_player: 1,
      pending: pending({ kind: "declare_blockers", player: 0 }),
    });
    expect(groupForDecision(state, [cast, pass], false, false)).toBe("acts");
  });

  it("assumes the board can decide when nobody says otherwise", () => {
    // The default matters: every other caller, and every other decision, is
    // unchanged by the argument existing.
    const state = view({
      phase: "combat",
      pending: pending({ kind: "declare_attackers", player: 0 }),
    });
    expect(groupForDecision(state, [cast, pass], false)).toBe("board");
    expect(groupForDecision(state, [cast, pass], false, true)).toBe("board");
  });
});

describe("your main phase", () => {
  it("sends the ring to the hand when there is something to play", () => {
    expect(groupForDecision(view(), [cast, pass], false)).toBe("hand");
  });

  it("sends it to the panel when there is nothing castable", () => {
    // A hand of things you cannot afford is not a reason to go to the hand --
    // and `groupsPresent` would decline an empty one anyway, which would look
    // like the button not working rather than like a decision.
    const activate = action({ id: "a2", kind: "activate" });
    expect(groupForDecision(view(), [activate, pass], false)).toBe("acts");
  });

  it("leaves it alone on somebody else's main phase", () => {
    const state = view({ active_player: 1, priority_player: 0 });
    expect(groupForDecision(state, [cast, pass], false)).toBe("acts");
  });
});

describe("leaving the ring alone", () => {
  it("says nothing when the decision is not yours", () => {
    const state = view({ pending: pending({ kind: "choose_target", player: 1 }) });
    expect(groupForDecision(state, [cast, pass], false)).toBeNull();
  });

  it("says nothing while somebody else holds priority", () => {
    // The AI is thinking, or another human is. Reading the board is what a
    // player does during it, and taking the ring off what they are reading is
    // the eager-rule failure this guard exists for.
    const state = view({ priority_player: 1 });
    expect(groupForDecision(state, [cast, pass], false)).toBeNull();
  });

  it("says nothing when a dialog owns the decision", () => {
    /*
     * A modal traps the ring itself (`stopRoot`), so moving it first would put
     * it somewhere the trap is about to take it away from -- one move, then
     * another, and the second looks like a glitch.
     */
    const state = view({ pending: pending({ kind: "mulligan", player: 0 }) });
    expect(groupForDecision(state, [cast, pass], true)).toBeNull();
  });

  it("says nothing when passing is the only thing to say", () => {
    // A step whose only legal action is passing does not deserve the ring being
    // taken off whatever the player was reading.
    expect(groupForDecision(view({ phase: "upkeep" }), [pass], false)).toBeNull();
  });
});

describe("the stack", () => {
  /*
   * Somebody else's removal is waiting on you. The engine stops there even
   * with nothing to answer it with, and the stop is only worth its press if
   * the card is being read -- so the ring goes to it, holding an answer or not.
   */
  it("goes to an opponent's spell waiting on you", () => {
    const state = view({
      active_player: 1,
      stack: [stackItem({ sid: 7, controller: 1 })],
    });
    expect(opponentTop(state)).toBe(7);
    expect(groupForDecision(state, [pass], false)).toBe("stack");
    expect(groupForDecision(state, [cast, pass], false)).toBe("stack");
  });

  it("keys on their newest item, so answering it is not a new decision", () => {
    // Your response on top of theirs must not read as a fresh threat and pull
    // the ring off what you just pressed.
    const state = view({
      active_player: 1,
      stack: [stackItem({ sid: 7, controller: 1 }), stackItem({ sid: 8, controller: 0 })],
    });
    expect(opponentTop(state)).toBe(7);
  });

  it("leaves your own spell alone", () => {
    const state = view({ stack: [stackItem({ sid: 3, controller: 0 })] });
    expect(opponentTop(state)).toBeNull();
    expect(groupForDecision(state, [cast, pass], false)).toBe("hand");
  });

  it("waits for priority to be yours", () => {
    const state = view({
      active_player: 1,
      priority_player: 1,
      stack: [stackItem({ sid: 7, controller: 1 })],
    });
    expect(opponentTop(state)).toBeNull();
    expect(groupForDecision(state, [pass], false)).toBeNull();
  });
});

describe("one pick of a permanent", () => {
  it("goes to the panel's mirror, which `useTableRegions` overrides with a card it can land on", () => {
    const { state, actions } = chooseTarget();
    expect(groupForDecision(state, actions, false)).toBe("acts");
  });
});
