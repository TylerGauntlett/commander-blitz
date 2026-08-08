/**
 * The mana row and the "why is this dim?" hint.
 *
 * The property worth guarding here is honesty. The row must never claim more
 * mana than the board can make, and it must never resolve an ambiguous source
 * into a colour the player has not chosen yet.
 */

import { describe, expect, it } from "vitest";
import type { ManaView } from "../src/api/types";
import {
  formatManaRow,
  manaRow,
  markSpent,
  sourcesSpentBy,
  unplayableHint,
} from "../src/logic/mana";
import { action, card } from "./fixtures";

function mana(overrides: Partial<ManaView> = {}): ManaView {
  return { pool: {}, sources: [], total: 0, ...overrides };
}

const forest = (oid: number) => ({ oid, options: [["G"]], symbols: ["G"], amount: 1 });
/** "{T}: Add {G} or {U}" -- one mana, either colour. */
const dual = (oid: number) => ({
  oid,
  options: [["G"], ["U"]],
  symbols: ["U", "G"],
  amount: 1,
});
/** "{T}: Add {G}{U}" -- two mana, one of each. */
const bounce = (oid: number) => ({
  oid,
  options: [["G", "U"]],
  symbols: ["U", "G"],
  amount: 2,
});

describe("manaRow", () => {
  it("is empty for a board with nothing untapped", () => {
    expect(manaRow(mana())).toEqual([]);
  });

  it("survives a missing payload rather than throwing", () => {
    expect(manaRow(undefined)).toEqual([]);
  });

  it("gives one pip per land", () => {
    const pips = manaRow(mana({ sources: [forest(1), forest(2)], total: 2 }));
    expect(pips).toHaveLength(2);
    expect(pips.every((p) => p.tone === "G")).toBe(true);
  });

  it("puts floating mana first, and marks it", () => {
    const pips = manaRow(mana({ pool: { U: 1 }, sources: [forest(1)], total: 2 }));
    expect(pips.map((p) => p.tone)).toEqual(["U", "G"]);
    expect(pips[0].floating).toBe(true);
    expect(pips[1].floating).toBe(false);
  });

  it("orders pool pips WUBRG rather than by object key order", () => {
    const pips = manaRow(mana({ pool: { G: 1, W: 1, B: 1 }, total: 3 }));
    expect(pips.map((p) => p.tone)).toEqual(["W", "B", "G"]);
  });

  describe("ambiguity", () => {
    it("draws a choice-dual as ONE undecided pip", () => {
      const pips = manaRow(mana({ sources: [dual(1)], total: 1 }));
      expect(pips).toHaveLength(1);
      expect(pips[0].tone).toBe("any");
      expect(pips[0].symbols).toEqual(["U", "G"]);
    });

    it("draws an add-both dual as TWO decided pips", () => {
      const pips = manaRow(mana({ sources: [bounce(1)], total: 2 }));
      expect(pips).toHaveLength(2);
      // Option order, i.e. the order the card writes them in -- these two came
      // out of one permanent and reading them in its order keeps that legible.
      expect(pips.map((p) => p.tone)).toEqual(["G", "U"]);
      expect(pips.every((p) => p.symbols.length === 1)).toBe(true);
    });

    it("never invents mana: pip count always equals the server's total", () => {
      for (const sources of [
        [forest(1)],
        [dual(1)],
        [bounce(1)],
        [forest(1), dual(2), bounce(3)],
      ]) {
        const total = sources.reduce((sum, s) => sum + s.amount, 0);
        expect(manaRow(mana({ sources, total }))).toHaveLength(total);
      }
    });
  });
});

describe("formatManaRow", () => {
  it("writes {0} for nothing", () => {
    expect(formatManaRow([])).toBe("{0}");
  });

  it("writes decided pips as their symbol", () => {
    expect(formatManaRow(manaRow(mana({ sources: [forest(1), forest(2)], total: 2 })))).toBe(
      "{G}{G}",
    );
  });

  it("writes an undecided pip as {?} rather than guessing", () => {
    expect(formatManaRow(manaRow(mana({ sources: [dual(1)], total: 1 })))).toBe("{?}");
  });
});

describe("unplayableHint", () => {
  it("says nothing when the card is playable", () => {
    expect(unplayableHint(card(), undefined, mana())).toBeNull();
  });

  it("spells out the shortfall for a mana problem", () => {
    const hint = unplayableHint(
      card({ mana_cost: "{2}{G}" }),
      "mana",
      mana({ sources: [forest(1)], total: 1 }),
    );
    expect(hint).toBe("Needs {2}{G} — you have {G}");
  });

  it("distinguishes a land's timing problem from a spell's", () => {
    const land = unplayableHint(card({ types: ["Land"] }), "timing", mana());
    const spell = unplayableHint(card({ types: ["Sorcery"] }), "timing", mana());
    expect(land).toMatch(/main phase/i);
    expect(spell).toMatch(/sorcery speed/i);
    expect(land).not.toBe(spell);
  });

  it.each([
    ["priority", /not your turn/i],
    ["land_drop", /land drop/i],
    ["targets", /no legal target/i],
  ] as const)("explains %s", (reason, pattern) => {
    expect(unplayableHint(card(), reason, mana())).toMatch(pattern);
  });

  it("gives every reason a distinct message", () => {
    const reasons = ["priority", "timing", "land_drop", "mana", "targets"] as const;
    const messages = reasons.map((r) => unplayableHint(card(), r, mana()));
    expect(new Set(messages).size).toBe(reasons.length);
  });
});

/**
 * What a hovered spell would cost you.
 *
 * The row could say what you have but not what a play would leave you with,
 * which is the interesting question in a turn with two plays in it -- see
 * docs/playtest-feedback-02.md item 4. The answer is the engine's own solved
 * payment, arriving on the action as `pays`. Nothing here computes affordability
 * or picks lands; guessing is precisely what the `options` payload exists to
 * prevent, since two "{G} or {U}" duals can pay {G}{U} but not {U}{U}.
 */
describe("sourcesSpentBy", () => {
  const cast = (oid: number, pays: number[]) =>
    action({ id: `a-${oid}`, kind: "cast", source_oid: oid, pays });

  it("finds the payment for the hovered card", () => {
    expect([...sourcesSpentBy([cast(9, [1, 2])], 9)]).toEqual([1, 2]);
  });

  it("is empty for a card no action names", () => {
    expect(sourcesSpentBy([cast(9, [1])], 10).size).toBe(0);
  });

  it("is empty when nothing is hovered over a card that cannot be cast", () => {
    expect(sourcesSpentBy([], 9).size).toBe(0);
  });

  it("ignores a land drop, which taps nothing", () => {
    const play = action({ kind: "play_land", source_oid: 9, pays: [] });
    expect(sourcesSpentBy([play], 9).size).toBe(0);
  });

  it("takes the first of several targetings, which all cost the same", () => {
    // One card with a choice of targets produces several cast actions. The
    // payment is a property of the card, not of the target.
    const a = action({ id: "a1", kind: "cast", source_oid: 9, pays: [1, 2] });
    const b = action({ id: "a2", kind: "cast", source_oid: 9, pays: [1, 2] });
    expect([...sourcesSpentBy([a, b], 9)]).toEqual([1, 2]);
  });
});

describe("markSpent", () => {
  it("marks the pips belonging to a tapped source", () => {
    const pips = manaRow(mana({ sources: [forest(1), forest(2)], total: 2 }));
    const marked = markSpent(pips, new Set([1]));
    expect(marked.map((pip) => pip.spent ?? false)).toEqual([true, false]);
  });

  it("marks every pip of a source that makes two mana", () => {
    // Tapping is what costs. A land that makes {G}{U} is gone for the step
    // whether the spell needed one of them or both, so claiming only half of it
    // would promise a mana the player cannot reach.
    const pips = manaRow(mana({ sources: [bounce(1)], total: 2 }));
    expect(markSpent(pips, new Set([1])).every((pip) => pip.spent)).toBe(true);
  });

  it("never marks floating mana", () => {
    // `Payment` does not itemise pool spend, so the pool is never claimed.
    const pips = manaRow(mana({ pool: { G: 2 }, sources: [forest(1)], total: 3 }));
    const marked = markSpent(pips, new Set([1]));
    expect(marked.filter((pip) => pip.floating).every((pip) => !pip.spent)).toBe(true);
  });

  it("returns the row untouched when nothing is being cast", () => {
    const pips = manaRow(mana({ sources: [forest(1)], total: 1 }));
    expect(markSpent(pips, new Set())).toBe(pips);
  });

  it("does not change how many pips there are", () => {
    // The row still says what you have. Marking is about what would leave.
    const pips = manaRow(mana({ sources: [forest(1), dual(2), bounce(3)], total: 4 }));
    expect(markSpent(pips, new Set([1, 3]))).toHaveLength(pips.length);
  });

  it("ignores a source that is no longer untapped", () => {
    // The forecast and the board can disagree for one frame while a response is
    // in flight; a stale oid must not mark somebody else's pip.
    const pips = manaRow(mana({ sources: [forest(1)], total: 1 }));
    expect(markSpent(pips, new Set([99])).some((pip) => pip.spent)).toBe(false);
  });
});
