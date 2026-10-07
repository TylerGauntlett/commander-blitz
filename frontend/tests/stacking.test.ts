import { describe, expect, it } from "vitest";
import { splitActionable, stackCards, stackKey } from "../src/logic/stacking";
import { card } from "./fixtures";

const forest = (overrides = {}) =>
  card({
    card_id: "forest",
    name: "Forest",
    types: ["Land"],
    power: null,
    toughness: null,
    ...overrides,
  });

describe("stackKey", () => {
  it("matches two identical permanents", () => {
    expect(stackKey(forest({ oid: 1 }))).toBe(stackKey(forest({ oid: 2 })));
  });

  it("separates tapped from untapped", () => {
    expect(stackKey(forest({ oid: 1, tapped: true }))).not.toBe(
      stackKey(forest({ oid: 2, tapped: false })),
    );
  });

  it("separates different counter loads", () => {
    const a = card({ oid: 1, counters: { "+1/+1": 1 } });
    const b = card({ oid: 2, counters: { "+1/+1": 2 } });
    expect(stackKey(a)).not.toBe(stackKey(b));
  });

  it("is stable regardless of counter key order", () => {
    const a = card({ oid: 1, counters: { "+1/+1": 1, charge: 2 } });
    const b = card({ oid: 2, counters: { charge: 2, "+1/+1": 1 } });
    expect(stackKey(a)).toBe(stackKey(b));
  });

  it("separates damaged from undamaged", () => {
    expect(stackKey(card({ oid: 1, damage: 1 }))).not.toBe(
      stackKey(card({ oid: 2, damage: 0 })),
    );
  });

  it("separates attacking from idle", () => {
    expect(stackKey(card({ oid: 1, attacking: true }))).not.toBe(stackKey(card({ oid: 2 })));
  });

  it("stacks a hasty newcomer with its ready twin: neither wears the hourglass", () => {
    expect(stackKey(card({ oid: 1, summoning_sick: true, keywords: ["haste"] }))).toBe(
      stackKey(card({ oid: 2, summoning_sick: false, keywords: ["haste"] })),
    );
  });

  it("separates summoning-sick from ready", () => {
    expect(stackKey(card({ oid: 1, summoning_sick: true }))).not.toBe(
      stackKey(card({ oid: 2, summoning_sick: false })),
    );
  });

  it("separates a commander from an ordinary copy", () => {
    expect(stackKey(card({ oid: 1, is_commander: true }))).not.toBe(stackKey(card({ oid: 2 })));
  });

  it("separates permanents held by different players", () => {
    expect(stackKey(forest({ oid: 1, controller: 0 }))).not.toBe(
      stackKey(forest({ oid: 2, controller: 1 })),
    );
  });
});

describe("stackCards", () => {
  it("collapses identical cards into one group", () => {
    const groups = stackCards([forest({ oid: 1 }), forest({ oid: 2 }), forest({ oid: 3 })]);
    expect(groups).toHaveLength(1);
    expect(groups[0].count).toBe(3);
    expect(groups[0].top.oid).toBe(1);
  });

  it("keeps a tapped copy out of the untapped stack", () => {
    const groups = stackCards([
      forest({ oid: 1 }),
      forest({ oid: 2, tapped: true }),
      forest({ oid: 3 }),
    ]);
    expect(groups).toHaveLength(2);
    expect(groups.map((g) => g.count)).toEqual([2, 1]);
  });

  it("preserves first-appearance order", () => {
    const groups = stackCards([
      card({ oid: 1, card_id: "bear" }),
      forest({ oid: 2 }),
      card({ oid: 3, card_id: "bear" }),
    ]);
    expect(groups.map((g) => g.top.card_id)).toEqual(["bear", "forest"]);
  });

  it("returns nothing for an empty battlefield", () => {
    expect(stackCards([])).toEqual([]);
  });

  it("hands a host its attachments", () => {
    const bear = card({ oid: 1, card_id: "bear" });
    const aura = card({ oid: 9, card_id: "pump", attached_to: 1 });
    const groups = stackCards([bear], new Map([[1, [aura]]]));
    expect(groups[0].attachments.map((c) => c.oid)).toEqual([9]);
  });

  it("never merges an enchanted permanent with a bare copy of the same card", () => {
    // `stackKey` describes a card, not what is hanging off it, so without this
    // the enchanted bear would hide behind the plain one and take its aura --
    // a whole permanent -- off the board with it.
    const aura = card({ oid: 9, card_id: "pump", attached_to: 1 });
    const groups = stackCards(
      [card({ oid: 1, card_id: "bear" }), card({ oid: 2, card_id: "bear" })],
      new Map([[1, [aura]]]),
    );
    expect(groups).toHaveLength(2);
    expect(groups.map((g) => g.attachments.length)).toEqual([1, 0]);
  });

  it("leaves attachments empty when none were passed", () => {
    const groups = stackCards([forest({ oid: 1 }), forest({ oid: 2 })]);
    expect(groups[0].attachments).toEqual([]);
  });
});

describe("splitActionable", () => {
  it("leaves a group alone when nothing in it is actionable", () => {
    const [group] = stackCards([forest({ oid: 1 }), forest({ oid: 2 })]);
    expect(splitActionable(group, new Set())).toEqual([group]);
  });

  it("leaves a group alone when every member is actionable", () => {
    const [group] = stackCards([forest({ oid: 1 }), forest({ oid: 2 })]);
    expect(splitActionable(group, new Set([1, 2]))).toEqual([group]);
  });

  it("splits out the members a legal action names", () => {
    const [group] = stackCards([forest({ oid: 1 }), forest({ oid: 2 }), forest({ oid: 3 })]);
    const parts = splitActionable(group, new Set([2]));
    expect(parts).toHaveLength(2);
    expect(parts[0].cards.map((c) => c.oid)).toEqual([2]);
    expect(parts[1].cards.map((c) => c.oid)).toEqual([1, 3]);
  });

  it("never splits a single card", () => {
    const [group] = stackCards([forest({ oid: 1 })]);
    expect(splitActionable(group, new Set([1]))).toEqual([group]);
  });

  it("gives the split groups distinct keys", () => {
    const [group] = stackCards([forest({ oid: 1 }), forest({ oid: 2 })]);
    const parts = splitActionable(group, new Set([1]));
    expect(parts[0].key).not.toBe(parts[1].key);
  });
});
