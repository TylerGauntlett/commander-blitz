/**
 * Which options a query leaves, and in what order.
 *
 * The order is the half worth testing on its own: `Enter` commits the
 * highlighted row, so "elf" landing on Elf rather than on Elf Warrior or
 * Werewolf is the difference between a combobox and a lottery.
 */

import { describe, expect, it } from "vitest";
import { COMBO_MIN, fold, narrow } from "../src/logic/promptFilter";
import { discardToHandSize } from "../src/testing/scenarios";

const items = (...texts: string[]) => texts.map((text) => ({ text }));
const texts = (rows: { text: string }[]) => rows.map((row) => row.text);

describe("fold", () => {
  it("ignores case", () => {
    expect(fold("Vampire")).toBe("vampire");
  });

  it("strips the diacritic nobody types", () => {
    expect(fold("Jötun")).toBe("jotun");
    expect(fold("Lim-Dûl")).toBe("lim-dul");
  });
});

describe("narrow", () => {
  it("returns the list untouched for an empty query", () => {
    const all = items("Advisor", "Angel", "Ape");
    // The same array, not merely an equal one: the unfiltered list is the
    // common case and re-sorting it would cost a render for nothing.
    expect(narrow(all, "")).toBe(all);
    expect(narrow(all, "   ")).toBe(all);
  });

  it("matches anywhere in the label", () => {
    expect(texts(narrow(items("Werewolf", "Angel", "Wolf"), "wolf"))).toEqual([
      "Wolf",
      "Werewolf",
    ]);
  });

  it("ANDs the terms, so a second word narrows", () => {
    const all = items("Elf Warrior", "Elf", "Human Warrior");
    expect(texts(narrow(all, "elf w"))).toEqual(["Elf Warrior"]);
  });

  it("puts the exact match first, then the prefix, then the rest", () => {
    const all = items("Wood Elf", "Elf Warrior", "Elemental", "Elf");
    expect(texts(narrow(all, "elf"))).toEqual(["Elf", "Elf Warrior", "Wood Elf"]);
  });

  it("keeps the engine's alphabetical order inside a band", () => {
    const all = items("Elf Archer", "Elf Berserker", "Elf Cleric");
    expect(texts(narrow(all, "elf"))).toEqual(["Elf Archer", "Elf Berserker", "Elf Cleric"]);
  });

  it("finds a folded label from an unfolded query, and the reverse", () => {
    expect(texts(narrow(items("Jötun"), "jot"))).toEqual(["Jötun"]);
    expect(texts(narrow(items("Jotun"), "jöt"))).toEqual(["Jotun"]);
  });

  it("answers nothing rather than everything when nothing matches", () => {
    expect(narrow(items("Advisor", "Angel"), "zzz")).toEqual([]);
  });
});

describe("COMBO_MIN", () => {
  /*
   * THE GUARD ON THE THRESHOLD.
   *
   * Lowering it under a decision that ships today would silently rebuild a
   * surface nobody asked to change -- discarding to hand size would stop being
   * a row of cards and start being a search field.
   */
  it("sits above the longest decision that ships as a row of buttons", () => {
    expect(discardToHandSize().actions.length).toBeLessThanOrEqual(COMBO_MIN);
  });
});
