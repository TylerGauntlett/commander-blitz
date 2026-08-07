/**
 * The mana row and the "why is this dim?" hint.
 *
 * The property worth guarding here is honesty. The row must never claim more
 * mana than the board can make, and it must never resolve an ambiguous source
 * into a colour the player has not chosen yet.
 */

import { describe, expect, it } from "vitest";
import type { ManaView } from "../src/api/types";
import { formatManaRow, manaRow, unplayableHint } from "../src/logic/mana";
import { card } from "./fixtures";

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
