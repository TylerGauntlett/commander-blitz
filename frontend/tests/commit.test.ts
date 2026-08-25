/**
 * What `X` presses, wherever the ring is.
 *
 * One rule with two consumers -- `Table.secondary` presses it and
 * `logic/verbs.ts` prints its name -- so what these pin is the ORDER, which is
 * the whole of it, and the two places it deliberately declines to answer.
 *
 * The order matters more than it looks. Every decision here ends at one control
 * and `X` is a hotkey for it, so a rule that reached one step further than the
 * player expected would submit a combat they were still arranging.
 */

import { describe, expect, it } from "vitest";
import type { CardView, GameView } from "../src/api/types";
import { COMMIT_TESTID, commitmentFor } from "../src/logic/commit";
import type { Staging } from "../src/logic/verbs";
import { action, card, gameView, pending, player } from "./fixtures";

const staging = (overrides: Partial<Staging> = {}): Staging => ({
  stagedAttacks: {},
  stagedBlocks: {},
  selectedOid: null,
  targeting: false,
  ...overrides,
});

function creature(
  oid: number,
  controller = 0,
  power = 2,
  toughness = 2,
  keywords: string[] = [],
): CardView {
  return card({
    oid,
    name: `C${oid}`,
    types: ["Creature"],
    zone: "battlefield",
    controller,
    owner: controller,
    power,
    toughness,
    keywords,
  });
}

const swing = (attacker: number, defender = 1) =>
  action({
    id: `atk-${attacker}`,
    kind: "add_attacker",
    source_oid: attacker,
    targets: [{ kind: "player", id: defender }],
  });

const block = (blocker: number, attacker: number) =>
  action({
    id: `blk-${blocker}-${attacker}`,
    kind: "add_blocker",
    source_oid: blocker,
    targets: [{ kind: "object", id: attacker }],
  });

const finish = action({ id: "fin", kind: "finish_declaration" });
const pass = action({ id: "p", kind: "pass" });

function board(cards: CardView[], kind: string | null): GameView {
  return gameView({
    seat: 0,
    battlefield: cards,
    players: [player({ pid: 0 }), player({ pid: 1, hand: null })],
    pending: kind ? pending({ kind, player: 0 }) : null,
  });
}

describe("a priority window", () => {
  it("is Pass", () => {
    expect(commitmentFor(board([], null), [pass], staging())).toEqual({
      target: "pass",
      verb: "Pass",
      actionId: "p",
    });
  });

  it("says nothing when passing is not legal", () => {
    expect(commitmentFor(board([], null), [], staging())).toBeNull();
  });

  it("says NOTHING while a spell is waiting for a target", () => {
    /*
     * `act()` ends targeting on its way out, so a fall-through to Pass here
     * would abandon a half-cast spell and give up priority in one press -- from
     * a button whose whole promise is that it presses the obvious thing. `B` is
     * how you back out of a selection.
     */
    expect(commitmentFor(board([], null), [pass], staging({ targeting: true }))).toBeNull();
  });

  it("is not somebody else's decision", () => {
    const theirs = gameView({
      seat: 0,
      players: [player({ pid: 0 }), player({ pid: 1, hand: null })],
      pending: pending({ kind: "declare_blockers", player: 1 }),
    });
    // Their declaration, your priority window: `X` is still your Pass.
    expect(commitmentFor(theirs, [pass], staging())?.verb).toBe("Pass");
  });
});

describe("declaring attackers", () => {
  const state = board([creature(1), creature(2)], "declare_attackers");

  it("stages the sensible attack while nothing is staged", () => {
    const got = commitmentFor(state, [swing(1), swing(2), finish], staging());
    expect(got).toEqual({ target: "all", verb: "All attack", actionId: null });
  });

  it("SUBMITS once something is staged, which is the order that matters", () => {
    /*
     * The first press stages and does not submit -- that is what makes this
     * safe on a hotkey, because it is reversible and the bar changes to say so.
     * The second press is the one that commits.
     */
    const got = commitmentFor(
      state,
      [swing(1), swing(2), finish],
      staging({ stagedAttacks: { 1: 1 } }),
    );
    expect(got).toEqual({ target: "confirm", verb: "Attack", actionId: null });
  });

  it("declines when nothing can attack at all", () => {
    // The panel promotes "No attacks" to the whole bar here: declining IS the
    // decision, and there is nothing else on screen it could be taken instead of.
    const got = commitmentFor(board([], "declare_attackers"), [finish], staging());
    expect(got).toEqual({ target: "skip", verb: "No attacks", actionId: "fin" });
  });

  it("says nothing when there is not even a way to decline", () => {
    expect(commitmentFor(board([], "declare_attackers"), [], staging())).toBeNull();
  });
});

describe("declaring blockers", () => {
  it("stages the ranked defence while nothing is staged", () => {
    // A 3/4 in front of a 2/2 is free, so "All defend" has something to offer.
    const state = board([creature(1, 0, 3, 4), creature(9, 1, 2, 2)], "declare_blockers");
    const got = commitmentFor(state, [block(1, 9), finish], staging());
    expect(got).toEqual({ target: "all", verb: "All defend", actionId: null });
  });

  it("submits once something is staged", () => {
    const state = board([creature(1, 0, 3, 4), creature(9, 1, 2, 2)], "declare_blockers");
    const got = commitmentFor(
      state,
      [block(1, 9), finish],
      staging({ stagedBlocks: { 1: 9 } }),
    );
    expect(got).toEqual({ target: "confirm", verb: "Block", actionId: null });
  });

  it("SAYS NOTHING when every block would be a chump", () => {
    /*
     * The one place this deliberately stops short. "All defend" declines a
     * chump block, so the mark is disabled here -- and `X` goes quiet rather
     * than reaching past it to "No blocks". Taking the damage is a decision a
     * player makes; it is not what a hotkey should do while they still have
     * every creature on the board and the panel still has the row.
     */
    const state = board([creature(1, 0, 1, 1), creature(9, 1, 5, 5)], "declare_blockers");
    expect(commitmentFor(state, [block(1, 9), finish], staging())).toBeNull();
  });

  it("declines when nothing can block at all", () => {
    const got = commitmentFor(board([], "declare_blockers"), [finish], staging());
    expect(got).toEqual({ target: "skip", verb: "No blocks", actionId: "fin" });
  });
});

describe("the controls it names", () => {
  it("names a testid the panel actually renders for each target", () => {
    // A rename in `ActionPanel` that did not come here would make `X` silently
    // stop working, which is exactly the failure this map exists to make loud.
    expect(COMMIT_TESTID).toEqual({
      all: "combat-all",
      confirm: "combat-confirm",
      skip: "combat-skip",
      pass: "commit",
    });
  });

  it("carries an action id for the two that are server actions, and not the others", () => {
    const staged = board([creature(1)], "declare_attackers");
    expect(commitmentFor(staged, [swing(1), finish], staging())?.actionId).toBeNull();
    expect(commitmentFor(board([], "declare_attackers"), [finish], staging())?.actionId).toBe(
      "fin",
    );
  });
});
