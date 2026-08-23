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
import { groupForDecision } from "../src/logic/focusGroup";
import { action, gameView, pending, player } from "./fixtures";

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
