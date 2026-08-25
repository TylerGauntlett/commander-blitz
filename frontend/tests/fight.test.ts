/**
 * What happens when two creatures fight.
 *
 * The arithmetic under both combat shortcuts, and the reason it is one module:
 * `blockTier` asks "does mine die, does theirs" and `attackTier` asks the same
 * two questions from the other side, so a keyword modelled in one and not the
 * other is a pair of buttons that disagree about the same two cards.
 *
 * The cases worth pinning are the ones power-and-toughness alone gets wrong --
 * deathtouch and first strike -- and the boundaries, because "exactly lethal"
 * is where every off-by-one in this file would live.
 */

import { describe, expect, it } from "vitest";
import type { CardView } from "../src/api/types";
import {
  couldBlock,
  effectiveToughness,
  killsInFight,
  strikesFirst,
  survivesFight,
  wouldKill,
} from "../src/logic/fight";
import { card } from "./fixtures";

function creature(
  power: number,
  toughness: number,
  keywords: string[] = [],
  extra: Partial<CardView> = {},
): CardView {
  return card({
    oid: 1,
    types: ["Creature"],
    zone: "battlefield",
    power,
    toughness,
    keywords,
    ...extra,
  });
}

describe("wouldKill", () => {
  it("is exactly-lethal damage", () => {
    expect(wouldKill(creature(2, 2), creature(2, 2))).toBe(true);
    expect(wouldKill(creature(1, 2), creature(2, 2))).toBe(false);
  });

  it("counts damage already marked on the target", () => {
    expect(wouldKill(creature(2, 2), creature(0, 3))).toBe(false);
    expect(wouldKill(creature(2, 2), creature(0, 3, [], { damage: 1 }))).toBe(true);
  });

  it("makes any damage lethal from a deathtouch source", () => {
    expect(wouldKill(creature(1, 1, ["Deathtouch"]), creature(10, 10))).toBe(true);
  });

  it("still needs damage to have happened", () => {
    // Zero power deals nothing, and "any nonzero amount is lethal" is a rule
    // about damage that was actually dealt.
    expect(wouldKill(creature(0, 4, ["Deathtouch"]), creature(2, 2))).toBe(false);
  });

  it("reads the keyword whatever case the engine sends it in", () => {
    expect(wouldKill(creature(1, 1, ["deathtouch"]), creature(10, 10))).toBe(true);
    expect(wouldKill(creature(1, 1, ["DEATHTOUCH"]), creature(10, 10))).toBe(true);
  });
});

describe("first strike", () => {
  it("counts double strike as first strike, which is the only question asked", () => {
    expect(strikesFirst(creature(1, 1, ["Double strike"]))).toBe(true);
  });

  it("lets a first striker walk away from a fight it wins", () => {
    // 2/2 first strike into a 3/2: it kills the 3/2 before taking anything.
    expect(survivesFight(creature(2, 2, ["First strike"]), creature(3, 2))).toBe(true);
    expect(survivesFight(creature(2, 2), creature(3, 2))).toBe(false);
  });

  it("does not save a first striker that fails to kill", () => {
    expect(survivesFight(creature(2, 2, ["First strike"]), creature(3, 3))).toBe(false);
  });

  it("cancels out when both have it", () => {
    const a = creature(2, 2, ["First strike"]);
    const b = creature(3, 2, ["First strike"]);
    expect(survivesFight(a, b)).toBe(false);
  });

  it("stops a creature killed first from killing anything", () => {
    // The 3/2 has lethal power for the 2/2, and never gets to use it.
    expect(wouldKill(creature(3, 2), creature(2, 2, ["First strike"]))).toBe(true);
    expect(killsInFight(creature(3, 2), creature(2, 2, ["First strike"]))).toBe(false);
  });

  it("does not stop one that survives the first strike", () => {
    expect(killsInFight(creature(3, 3), creature(2, 2, ["First strike"]))).toBe(true);
  });
});

describe("deathtouch in a fight", () => {
  it("trades a 1/1 for anything", () => {
    const mouse = creature(1, 1, ["Deathtouch"]);
    const giant = creature(5, 5);
    expect(killsInFight(mouse, giant)).toBe(true);
    expect(survivesFight(mouse, giant)).toBe(false);
  });

  it("loses to first strike, which is the interaction that decides it", () => {
    const mouse = creature(1, 1, ["Deathtouch"]);
    const knight = creature(2, 2, ["First strike"]);
    expect(killsInFight(mouse, knight)).toBe(false);
    expect(survivesFight(knight, mouse)).toBe(true);
  });
});

describe("effectiveToughness", () => {
  it("is toughness less damage already marked", () => {
    expect(effectiveToughness(creature(2, 5, [], { damage: 2 }))).toBe(3);
  });
});

describe("couldBlock", () => {
  it("refuses a tapped creature", () => {
    expect(couldBlock(creature(2, 2, [], { tapped: true }), creature(1, 1))).toBe(false);
  });

  it("refuses a permanent that is not a creature", () => {
    const rock = card({ types: ["Artifact"], zone: "battlefield", power: null });
    expect(couldBlock(rock, creature(1, 1))).toBe(false);
  });

  it("lets anything untapped block a ground creature", () => {
    expect(couldBlock(creature(0, 1), creature(9, 9))).toBe(true);
  });

  it("needs flying or reach against a flier", () => {
    const flier = creature(2, 2, ["Flying"]);
    expect(couldBlock(creature(9, 9), flier)).toBe(false);
    expect(couldBlock(creature(1, 1, ["Flying"]), flier)).toBe(true);
    expect(couldBlock(creature(1, 1, ["Reach"]), flier)).toBe(true);
  });

  it("does not treat reach as evasion on the attacking side", () => {
    // Reach is a blocking ability. A creature with reach and no flying is a
    // ground creature, and anything can block it.
    expect(couldBlock(creature(1, 1), creature(2, 2, ["Reach"]))).toBe(true);
  });
});
