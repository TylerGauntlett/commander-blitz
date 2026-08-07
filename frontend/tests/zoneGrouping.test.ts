import { describe, expect, it } from "vitest";
import { counterBadges, manaPips, statLine } from "../src/logic/cardStyle";
import { groupBattlefield, laneFor, seatOrder } from "../src/logic/zoneGrouping";
import { card, gameView, player } from "./fixtures";

describe("laneFor", () => {
  it("puts creatures in the creature lane", () => {
    expect(laneFor(card({ types: ["Creature"] }))).toBe("Creatures");
  });

  it("puts lands in the land lane", () => {
    expect(laneFor(card({ types: ["Land"] }))).toBe("Lands");
  });

  it("groups artifacts and enchantments together", () => {
    expect(laneFor(card({ types: ["Artifact"] }))).toBe("Artifacts & Enchantments");
    expect(laneFor(card({ types: ["Enchantment"] }))).toBe("Artifacts & Enchantments");
  });

  it("treats an artifact creature as a creature", () => {
    expect(laneFor(card({ types: ["Artifact", "Creature"] }))).toBe("Creatures");
  });

  it("falls back to Other", () => {
    expect(laneFor(card({ types: ["Planeswalker"] }))).toBe("Other");
  });
});

describe("groupBattlefield", () => {
  it("only includes the requested controller", () => {
    const state = gameView({
      battlefield: [
        card({ oid: 1, controller: 0, types: ["Creature"] }),
        card({ oid: 2, controller: 1, types: ["Creature"] }),
        card({ oid: 3, controller: 0, types: ["Land"] }),
      ],
    });
    const mine = groupBattlefield(state, 0);
    expect(mine.Creatures.map((c) => c.oid)).toEqual([1]);
    expect(mine.Lands.map((c) => c.oid)).toEqual([3]);
    expect(groupBattlefield(state, 1).Creatures.map((c) => c.oid)).toEqual([2]);
  });

  it("preserves battlefield order within a lane", () => {
    const state = gameView({
      battlefield: [
        card({ oid: 7, types: ["Creature"] }),
        card({ oid: 3, types: ["Creature"] }),
      ],
    });
    expect(groupBattlefield(state, 0).Creatures.map((c) => c.oid)).toEqual([7, 3]);
  });
});

describe("seatOrder", () => {
  it("puts the viewer last so they render at the bottom", () => {
    const state = gameView({
      seat: 0,
      players: [player(), player({ pid: 1 }), player({ pid: 2 }), player({ pid: 3 })],
    });
    expect(seatOrder(state)).toEqual([1, 2, 3, 0]);
  });

  it("rotates for a different viewing seat", () => {
    const state = gameView({
      seat: 2,
      players: [player(), player({ pid: 1 }), player({ pid: 2 }), player({ pid: 3 })],
    });
    expect(seatOrder(state)).toEqual([3, 0, 1, 2]);
  });
});

describe("statLine", () => {
  it("shows remaining toughness on the battlefield", () => {
    expect(statLine(card({ power: 5, toughness: 5, damage: 2 }))).toBe("5/3");
  });

  it("shows printed toughness elsewhere", () => {
    expect(statLine(card({ zone: "hand", power: 5, toughness: 5, damage: 0 }))).toBe("5/5");
  });

  it("is empty for a non-creature", () => {
    expect(statLine(card({ power: null, toughness: null }))).toBe("");
  });
});

describe("counterBadges", () => {
  it("renders a multiplier only above one", () => {
    expect(counterBadges(card({ counters: { "+1/+1": 1 } }))).toEqual(["+1/+1"]);
    expect(counterBadges(card({ counters: { "+1/+1": 3 } }))).toEqual(["+1/+1 x3"]);
  });

  it("ignores empty counter maps", () => {
    expect(counterBadges(card({ counters: {} }))).toEqual([]);
  });
});

describe("manaPips", () => {
  it("splits a cost into symbols", () => {
    expect(manaPips("{4}{G}{U}").map((pip) => pip.symbol)).toEqual(["4", "G", "U"]);
  });

  it("gives repeated symbols distinct keys", () => {
    const keys = manaPips("{G}{G}").map((pip) => pip.key);
    expect(new Set(keys).size).toBe(2);
  });

  it("returns nothing for a free cost", () => {
    expect(manaPips("{0}")).toEqual([]);
    expect(manaPips("")).toEqual([]);
  });
});
