/**
 * "All attack" -- suggesting a swing worth making.
 *
 * The mirror of `autoBlock.test.ts`, and the tests that matter are the same
 * ones: it must never stage something a player would immediately have to undo,
 * and it must never invent an attack the server did not offer.
 *
 * The one rule here that is not about a single creature is the last block --
 * a board that can kill you on the swing back keeps everything that could block
 * at home, and only the creatures nothing can block still go.
 */

import { describe, expect, it } from "vitest";
import type { CardView, GameView } from "../src/api/types";
import { attackTier, autoAttacks, sensibleAttacks } from "../src/logic/autoAttack";
import { action, card, gameView, player } from "./fixtures";

function creature(
  oid: number,
  power: number,
  toughness: number,
  controller = 0,
  keywords: string[] = [],
  extra: Partial<CardView> = {},
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
    ...extra,
  });
}

/** The `add_attacker` action the server would emit for this pairing. */
function swing(attacker: number, defender = 1) {
  return action({
    id: `a${attacker}`,
    kind: "add_attacker",
    source_oid: attacker,
    targets: [{ kind: "player", id: defender }],
  });
}

function board(cards: CardView[], life = 40): GameView {
  return gameView({
    seat: 0,
    battlefield: cards,
    players: [player({ pid: 0, life }), player({ pid: 1, hand: null })],
  });
}

describe("attackTier", () => {
  it("is unopposed when nothing untapped is left to block", () => {
    expect(attackTier(creature(1, 1, 1), [])).toBe(1);
    expect(attackTier(creature(1, 1, 1), [creature(2, 5, 5, 1, [], { tapped: true })])).toBe(1);
  });

  it("is unopposed when a flier has nothing that can reach it", () => {
    const flier = creature(1, 2, 2, 0, ["Flying"]);
    expect(attackTier(flier, [creature(2, 9, 9, 1)])).toBe(1);
    expect(attackTier(flier, [creature(2, 2, 2, 1, ["Reach"])])).not.toBe(1);
  });

  it("is safe when it walks away from every block they could make", () => {
    // A 4/4 into a 2/2 and a 1/1: neither kills it.
    expect(attackTier(creature(1, 4, 4), [creature(2, 2, 2, 1), creature(3, 1, 1, 1)])).toBe(2);
  });

  it("is a trade when the blocks that kill it die for the trouble", () => {
    expect(attackTier(creature(1, 3, 3), [creature(2, 3, 3, 1)])).toBe(3);
  });

  it("is a loss when a blocker kills it and survives", () => {
    expect(attackTier(creature(1, 1, 1), [creature(2, 5, 5, 1)])).toBe(4);
  });

  it("takes the defender's BEST answer, not their first", () => {
    // The 3/3 would be a trade; the 5/5 eats it for free. A defender picks the
    // second, so this is a loss.
    expect(attackTier(creature(1, 3, 3), [creature(2, 3, 3, 1), creature(3, 5, 5, 1)])).toBe(4);
  });

  it("reads deathtouch on the blocker", () => {
    // A 1/5 is a wall a 4/4 walks past. Give it deathtouch and the same attack
    // dies for nothing -- one keyword, two tiers apart.
    expect(attackTier(creature(1, 4, 4), [creature(2, 1, 5, 1)])).toBe(2);
    expect(attackTier(creature(1, 4, 4), [creature(2, 1, 5, 1, ["Deathtouch"])])).toBe(4);
    // A 1/1 deathtouch is still only a trade: it dies to the four damage.
    expect(attackTier(creature(1, 4, 4), [creature(2, 1, 1, 1, ["Deathtouch"])])).toBe(3);
  });

  it("reads first strike on the attacker", () => {
    // 3/2 into a 3/3 is a trade. With first strike the 3/3 is dead before it
    // deals anything, so the same attack is free.
    expect(attackTier(creature(1, 3, 2), [creature(2, 3, 3, 1)])).toBe(3);
    expect(attackTier(creature(1, 3, 2, 0, ["First strike"]), [creature(2, 3, 3, 1)])).toBe(2);
  });
});

describe("autoAttacks", () => {
  it("suggests nothing when nothing can attack", () => {
    expect(autoAttacks(board([]), [])).toEqual([]);
  });

  it("never invents an attack the server did not offer", () => {
    // Two creatures on the battlefield, one `add_attacker` action.
    const state = board([creature(1, 2, 2), creature(2, 2, 2)]);
    expect(autoAttacks(state, [swing(1)]).map((p) => p.attacker)).toEqual([1]);
  });

  it("holds back a creature that dies for nothing", () => {
    const state = board([creature(1, 1, 1), creature(2, 5, 5, 1)]);
    expect(sensibleAttacks(state, [swing(1)])).toEqual([]);
    // ...and it is still in the full list, so the second press can send it.
    expect(autoAttacks(state, [swing(1)])).toEqual([{ attacker: 1, defender: 1, tier: 4 }]);
  });

  it("sends the ones worth sending and keeps the rest", () => {
    const state = board([
      creature(1, 4, 4), // safe against their 2/2
      creature(2, 1, 1), // dies to it for nothing
      creature(3, 2, 2, 1),
    ]);
    expect(sensibleAttacks(state, [swing(1), swing(2)]).map((p) => p.attacker)).toEqual([1]);
  });

  it("aims at the first legal defender, which is what pressing the card does", () => {
    const state = board([creature(1, 2, 2)]);
    expect(autoAttacks(state, [swing(1, 1)])[0].defender).toBe(1);
  });

  it("orders by tier so the first press stages the best attacks first", () => {
    const state = board([
      creature(1, 1, 1, 0, ["Flying"]), // unopposed
      creature(2, 4, 4), // safe
      creature(3, 3, 3), // trades
      creature(4, 2, 2, 1),
      creature(5, 3, 3, 1),
    ]);
    const tiers = autoAttacks(state, [swing(1), swing(2), swing(3)]).map((p) => p.tier);
    expect(tiers).toEqual([...tiers].sort());
  });

  it("is stable, so the same board always suggests the same attack", () => {
    const state = board([creature(1, 4, 4), creature(2, 4, 4), creature(3, 2, 2, 1)]);
    const once = autoAttacks(state, [swing(1), swing(2)]);
    const twice = autoAttacks(state, [swing(2), swing(1)]);
    expect(once).toEqual(twice);
  });
});

describe("when they can kill you on the swing back", () => {
  /*
   * A creature that is safe attacking is usually the creature that is useful
   * blocking, and those are the same turn. The rule is deliberately blunt --
   * total power against your life -- because it is the number a player glances
   * at, and a forecast the client cannot verify would be worse than a rule of
   * thumb it can state.
   */
  it("keeps everything that could block at home", () => {
    // Their board is 8 power; you are at 6. The 4/4 is safe to swing and is
    // also the only thing standing between you and the game.
    const state = board([creature(1, 4, 4), creature(2, 3, 3, 1), creature(3, 5, 5, 1)], 6);
    expect(sensibleAttacks(state, [swing(1)])).toEqual([]);
    expect(autoAttacks(state, [swing(1)])[0].tier).toBe(5);
  });

  it("still sends what nothing can block", () => {
    // A flier they cannot answer costs nothing at home: it was never going to
    // be in front of anything.
    const state = board(
      [
        creature(1, 2, 2, 0, ["Flying"]),
        creature(2, 4, 4),
        creature(3, 3, 3, 1),
        creature(4, 5, 5, 1),
      ],
      6,
    );
    const sent = sensibleAttacks(state, [swing(1), swing(2)]);
    expect(sent.map((p) => p.attacker)).toEqual([1]);
  });

  it("does not fire while you are comfortably ahead", () => {
    const state = board([creature(1, 4, 4), creature(2, 3, 3, 1)], 40);
    expect(sensibleAttacks(state, [swing(1)]).map((p) => p.attacker)).toEqual([1]);
  });
});
