/**
 * "All defend" -- suggesting blocks worth making.
 *
 * The ranking is the one a player uses without thinking about it, and the tests
 * that matter are the ones proving it never suggests something a player would
 * have to undo: no chump blocks, no creature assigned twice, and nothing outside
 * the server's legal-action list.
 */

import { describe, expect, it } from "vitest";
import { autoBlocks, blockTier } from "../src/logic/autoBlock";
import { action, card, gameView, player } from "./fixtures";

/** A creature on the battlefield with the given stats. */
function creature(oid: number, power: number, toughness: number, damage = 0) {
  return card({
    oid,
    name: `C${oid}`,
    types: ["Creature"],
    zone: "battlefield",
    power,
    toughness,
    damage,
  });
}

/** The `add_blocker` action the server would emit for this pairing. */
function block(blocker: number, attacker: number) {
  return action({
    id: `b${blocker}-${attacker}`,
    kind: "add_blocker",
    source_oid: blocker,
    targets: [{ kind: "object", id: attacker }],
  });
}

function board(cards: ReturnType<typeof creature>[]) {
  return gameView({ battlefield: cards, players: [player(), player({ pid: 1, hand: null })] });
}

describe("blockTier", () => {
  it("ranks survive-and-kill first", () => {
    expect(blockTier(creature(1, 3, 4), creature(2, 2, 2))).toBe(1);
  });

  it("ranks a wall second", () => {
    // Survives, cannot kill. You lose nothing and the damage stops.
    expect(blockTier(creature(1, 0, 5), creature(2, 2, 4))).toBe(2);
  });

  it("ranks a real trade third", () => {
    expect(blockTier(creature(1, 3, 2), creature(2, 3, 3))).toBe(3);
  });

  it("ranks a chump block last", () => {
    expect(blockTier(creature(1, 1, 1), creature(2, 5, 5))).toBe(4);
  });

  it("counts damage already marked against the blocker", () => {
    // A 3/4 that has taken 2 is effectively a 3/2 and no longer survives a 3/3.
    expect(blockTier(creature(1, 3, 4), creature(2, 3, 3))).toBe(1);
    expect(blockTier(creature(1, 3, 4, 2), creature(2, 3, 3))).toBe(3);
  });

  it("counts damage already marked against the attacker", () => {
    // A wounded attacker dies to less power than its printed toughness.
    expect(blockTier(creature(1, 2, 5), creature(2, 1, 3))).toBe(2);
    expect(blockTier(creature(1, 2, 5), creature(2, 1, 3, 1))).toBe(1);
  });

  it("treats exactly-lethal power as a kill and exactly-lethal damage as death", () => {
    // The boundary both ways: 2 power into 2 toughness kills, and is killed.
    expect(blockTier(creature(1, 2, 2), creature(2, 2, 2))).toBe(3);
  });
});

describe("autoBlocks", () => {
  it("suggests nothing when there is nothing to block", () => {
    expect(autoBlocks(board([]), [])).toEqual([]);
  });

  it("takes a free block", () => {
    const state = board([creature(1, 3, 4), creature(2, 2, 2)]);
    expect(autoBlocks(state, [block(1, 2)])).toEqual([{ blocker: 1, attacker: 2, tier: 1 }]);
  });

  it("refuses a chump block", () => {
    // Giving a creature away for nothing is a decision, not a default. It stays
    // one click away on the card itself.
    const state = board([creature(1, 1, 1), creature(2, 5, 5)]);
    expect(autoBlocks(state, [block(1, 2)])).toEqual([]);
  });

  it("prefers the better pairing when a blocker has a choice", () => {
    const state = board([creature(1, 3, 4), creature(2, 5, 5), creature(3, 2, 2)]);
    const chosen = autoBlocks(state, [block(1, 2), block(1, 3)]);
    // Blocking the 5/5 would be a chump; blocking the 2/2 is free.
    expect(chosen).toEqual([{ blocker: 1, attacker: 3, tier: 1 }]);
  });

  it("gives each blocker at most one attacker", () => {
    const state = board([creature(1, 3, 4), creature(2, 2, 2), creature(3, 2, 2)]);
    const chosen = autoBlocks(state, [block(1, 2), block(1, 3)]);
    expect(chosen).toHaveLength(1);
  });

  it("spreads blocks rather than ganging up", () => {
    // Two blockers, two attackers: one each. A default that quietly commits
    // both to the same attacker is a default that loses games.
    const state = board([
      creature(1, 3, 4),
      creature(2, 3, 4),
      creature(3, 2, 2),
      creature(4, 2, 2),
    ]);
    const chosen = autoBlocks(state, [block(1, 3), block(1, 4), block(2, 3), block(2, 4)]);
    expect(chosen).toHaveLength(2);
    expect(new Set(chosen.map((c) => c.attacker)).size).toBe(2);
    expect(new Set(chosen.map((c) => c.blocker)).size).toBe(2);
  });

  it("never invents a pairing the server did not offer", () => {
    // A menace or evasive attacker simply has no legal pair, so it has none here.
    const state = board([creature(1, 9, 9), creature(2, 1, 1)]);
    expect(autoBlocks(state, [])).toEqual([]);
  });

  it("is stable: the same board gives the same defence", () => {
    const state = board([creature(1, 3, 4), creature(2, 3, 4), creature(3, 2, 2)]);
    const actions = [block(2, 3), block(1, 3)];
    expect(autoBlocks(state, actions)).toEqual(autoBlocks(state, actions));
  });

  it("skips a card it cannot see rather than guessing at its stats", () => {
    const state = board([creature(1, 3, 4)]);
    expect(autoBlocks(state, [block(1, 99)])).toEqual([]);
  });
});
