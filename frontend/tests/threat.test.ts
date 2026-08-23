/**
 * The opponent summary.
 *
 * On a handheld this line IS the opponent -- their board is not drawn at a size
 * anybody can read, so every wrong number here is a decision made on bad
 * information. The cases worth pinning are the ones where a plausible
 * implementation is quietly wrong: counting mana symbols instead of sources,
 * counting a tapped creature as a blocker, or letting an Equipment inflate the
 * creature count.
 */

import { describe, expect, it } from "vitest";
import type { CardView } from "../src/api/types";
import { threatLine, threatOf, threatParts } from "../src/logic/threat";
import { card, gameView, player } from "../src/testing/fixtures";

const creature = (overrides: Partial<CardView> = {}): CardView =>
  card({
    types: ["Creature"],
    type_line: "Creature — Bear",
    zone: "battlefield",
    power: 2,
    toughness: 2,
    ...overrides,
  });

function board(cards: CardView[], seat = 1, manaSources = 0) {
  return gameView({
    battlefield: cards.map((c) => ({ ...c, controller: seat })),
    players: [
      player({ pid: 0 }),
      player({
        pid: seat,
        hand_count: 3,
        mana: {
          pool: {},
          total: manaSources,
          sources: Array.from({ length: manaSources }, (_, i) => ({
            oid: 900 + i,
            options: [["G"]],
            symbols: ["G"],
            amount: 1,
          })),
        },
      }),
    ],
  });
}

describe("threatOf", () => {
  it("counts an empty board as nothing, rather than refusing to answer", () => {
    const threat = threatOf(board([]), 1);
    expect(threat.creatures).toBe(0);
    expect(threat.power).toBe(0);
    expect(threat.untapped).toBe(0);
  });

  it("counts only untapped creatures as able to block", () => {
    const threat = threatOf(
      board([
        creature({ oid: 1 }),
        creature({ oid: 2, tapped: true }),
        creature({ oid: 3, tapped: true }),
      ]),
      1,
    );
    expect(threat.creatures).toBe(3);
    expect(threat.untapped).toBe(1);
  });

  it("counts power across every creature, tapped or not", () => {
    // A tapped attacker is still damage that exists; it just cannot block now.
    const threat = threatOf(
      board([creature({ oid: 1, power: 4 }), creature({ oid: 2, power: 3, tapped: true })]),
      1,
    );
    expect(threat.power).toBe(7);
  });

  it("treats a null power as zero rather than as NaN", () => {
    // Every non-creature permanent has null power, and so does a creature whose
    // characteristic-defining ability the view has not resolved.
    const threat = threatOf(board([creature({ oid: 1, power: null })]), 1);
    expect(threat.power).toBe(0);
    expect(Number.isNaN(threat.power)).toBe(false);
  });

  it("counts reach alongside flying, since both stop an evasive attack", () => {
    const threat = threatOf(
      board([
        creature({ oid: 1, keywords: ["Flying"] }),
        creature({ oid: 2, keywords: ["Reach"] }),
        creature({ oid: 3, keywords: ["Trample"] }),
      ]),
      1,
    );
    expect(threat.fliers).toBe(2);
  });

  it("counts mana SOURCES, never symbols", () => {
    /*
     * The distinction `ManaView` documents: "Add {G} or {U}" is one mana. A
     * summary that counted symbols would tell the reader an opponent can hold
     * up twice what they really can, which is the worst direction to be wrong
     * in during a combat decision.
     */
    const state = board([], 1, 0);
    state.players[1].mana = {
      pool: {},
      total: 2,
      sources: [{ oid: 900, options: [["G"], ["U"]], symbols: ["G", "U"], amount: 1 }],
    };
    expect(threatOf(state, 1).openMana).toBe(1);
  });

  it("keeps non-creature permanents out of the creature count", () => {
    const threat = threatOf(
      board([
        creature({ oid: 1 }),
        card({
          oid: 2,
          types: ["Artifact"],
          type_line: "Artifact",
          zone: "battlefield",
        }),
        card({ oid: 3, types: ["Land"], type_line: "Land", zone: "battlefield" }),
      ]),
      1,
    );
    expect(threat.creatures).toBe(1);
    expect(threat.other).toBe(1);
  });

  it("ignores permanents another seat controls", () => {
    const state = board([creature({ oid: 1 })], 1);
    state.battlefield.push({ ...creature({ oid: 2, power: 9 }), controller: 0 });
    expect(threatOf(state, 1).power).toBe(2);
  });
});

describe("threatParts", () => {
  it("always says the creature count, because 'nothing on board' is the useful case", () => {
    const parts = threatParts(threatOf(board([]), 1));
    expect(parts.map((p) => p.key)).toEqual(["creatures"]);
  });

  it("drops empty clauses so a narrow line is not spent on zeroes", () => {
    const threat = threatOf(board([creature({ oid: 1, tapped: true })]), 1);
    expect(threatParts(threat).map((p) => p.key)).toEqual(["creatures", "power"]);
  });

  it("keeps a single flier, which is exactly the fact that changes a decision", () => {
    const threat = threatOf(board([creature({ oid: 1, keywords: ["Flying"] })]), 1);
    expect(threatParts(threat).map((p) => p.key)).toContain("fliers");
  });
});

describe("threatLine", () => {
  it("pluralises countable nouns and leaves mass nouns alone", () => {
    // "2 untappeds" and "7 powers" is what a naive pluraliser produces, and a
    // summary with a grammar mistake is one the reader stops trusting.
    const threat = threatOf(
      board([creature({ oid: 1, power: 4 }), creature({ oid: 2, power: 3 })], 1, 2),
      1,
    );
    expect(threatLine(threat)).toBe("2 creatures · 2 untapped · 7 power · 2 open");
  });

  it("says one creature in the singular", () => {
    expect(threatLine(threatOf(board([creature({ oid: 1, power: 0 })]), 1))).toBe(
      "1 creature · 1 untapped",
    );
  });
});
