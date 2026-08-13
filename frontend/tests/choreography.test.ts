/**
 * Combat, as a plan.
 *
 * These assert the *shape* of an exchange rather than any pixel of it: who is
 * told to move, what lands where, and -- the point of the whole module -- that
 * a swing collapses into a couple of beats instead of queuing up nine.
 */

import { describe, expect, it } from "vitest";
import type { GameEvent } from "../src/api/types";
import { planCombat } from "../src/logic/choreography";
import type { Beat, TimedFx } from "../src/logic/events";

const SILENT = (type: string) =>
  [
    "combat_damage_to_player",
    "dies",
    "leaves_battlefield",
    "step_began",
    "step_ended",
  ].includes(type);

function event(
  type: string,
  data: Record<string, unknown> = {},
  extra: Partial<GameEvent> = {},
): GameEvent {
  return { type, turn: 4, step: 8, player: 0, source: null, data, ...extra };
}

function of<K extends TimedFx["kind"]>(beat: Beat | undefined, kind: K) {
  return (beat?.fx ?? []).filter((fx): fx is Extract<TimedFx, { kind: K }> => fx.kind === kind);
}

/** One attacker, one blocker, a trade. */
const TRADE: GameEvent[] = [
  event("attackers_declared", { attackers: [11] }),
  event("attacks", { attacker: 11, defender: 1 }, { source: 11 }),
  event("blocks", { blocker: 21, attacker: 11 }, { player: 1, source: 21 }),
  event("damage_dealt", { amount: 3, to: "permanent", oid: 21, combat: true }, { source: 11 }),
  event("damage_dealt", { amount: 3, to: "permanent", oid: 11, combat: true }, { source: 21 }),
];

describe("planCombat", () => {
  it("collapses a whole exchange into a declaration and a strike", () => {
    const plan = planCombat(TRADE, SILENT, 0);
    expect(plan.leaders.size).toBe(3); // attack, block, strike
    // Five events, three of which lead a run: the other two are folded in.
    expect(plan.absorbed.size).toBe(2);
  });

  it("sends attackers at the player they declared against", () => {
    const plan = planCombat(TRADE, SILENT, 0);
    const declare = plan.leaders.get(0);
    expect(of(declare, "actuate")).toMatchObject([
      { oid: 11, move: "lunge", toward: { kind: "player", pid: 1 } },
    ]);
  });

  it("sends blockers at the attacker they blocked", () => {
    const plan = planCombat(TRADE, SILENT, 0);
    const block = plan.leaders.get(2);
    expect(of(block, "actuate")).toMatchObject([
      { oid: 21, move: "lunge", toward: { kind: "object", oid: 11 } },
    ]);
  });

  /**
   * The constraint that decides the whole strike.
   *
   * A blocker in a trade both deals and takes damage. Telling it to lunge *and*
   * to recoil would cancel the lunge at the moment of contact and snap the card
   * back from full extension, because an actuator drops whatever the card was
   * already doing. So only the attacking side moves under its own power.
   */
  it("lunges the attacker only, and knocks the blocker back", () => {
    const plan = planCombat(TRADE, SILENT, 0);
    const strike = plan.leaders.get(3);
    const moves = of(strike, "actuate");
    expect(moves.filter((m) => m.move === "lunge")).toMatchObject([{ oid: 11 }]);
    expect(moves.filter((m) => m.move === "recoil")).toMatchObject([{ oid: 21 }]);
    // The attacker takes damage too, but it is mid-swing: rattled, not shoved.
    expect(moves.filter((m) => m.move === "shudder")).toMatchObject([{ oid: 11 }]);
  });

  it("puts the sparks and the numeral at the point the two cards meet", () => {
    const plan = planCombat(TRADE, SILENT, 0);
    const strike = plan.leaders.get(3);
    for (const fx of [...of(strike, "emit"), ...of(strike, "float")]) {
      expect(fx.at_point).toMatchObject({ kind: "between" });
    }
  });

  it("plays every hit at once rather than one after another", () => {
    const plan = planCombat(TRADE, SILENT, 0);
    const strike = plan.leaders.get(3);
    const offsets = of(strike, "emit").map((fx) => fx.at);
    // Scattered by a few frames so it reads as a melee, but nowhere near the
    // 340ms-per-hit the old queue spent.
    expect(Math.max(...offsets) - Math.min(...offsets)).toBeLessThan(80);
  });

  it("shakes the screen for damage to a player, not for creatures trading", () => {
    const trade = planCombat(TRADE, SILENT, 0);
    expect(of(trade.leaders.get(3), "shake")).toHaveLength(0);

    const through = planCombat(
      [
        event("attacks", { attacker: 11, defender: 1 }, { source: 11 }),
        event(
          "damage_dealt",
          { amount: 7, to: "player", combat: true },
          { player: 1, source: 11 },
        ),
      ],
      SILENT,
      0,
    );
    expect(of(through.leaders.get(1), "shake")).toHaveLength(1);
  });

  it("tints the screen edge only when the hit lands on the viewer", () => {
    const build = (victim: number) =>
      planCombat(
        [
          event("attacks", { attacker: 11, defender: victim }, { source: 11 }),
          event(
            "damage_dealt",
            { amount: 5, to: "player", combat: true },
            { player: victim, source: 11 },
          ),
        ],
        SILENT,
        0,
      );
    expect(of(build(0).leaders.get(1), "vignette")).toHaveLength(1);
    expect(of(build(1).leaders.get(1), "vignette")).toHaveLength(0);
  });

  /**
   * Burn is not combat, and the difference is visible.
   *
   * A Lightning Bolt has no creature on the battlefield to travel from -- its
   * source is a card on the stack -- so the sparks land on the victim itself
   * and nothing lunges.
   */
  it("lands a non-combat hit on the victim, with nothing lunging", () => {
    const plan = planCombat(
      [event("damage_dealt", { amount: 3, to: "permanent", oid: 42 })],
      SILENT,
      0,
    );
    const beat = plan.leaders.get(0);
    expect(of(beat, "emit")[0].at_point).toMatchObject({ kind: "object", oid: 42 });
    expect(of(beat, "actuate").filter((m) => m.move === "lunge")).toHaveLength(0);
  });

  it("collapses a storm of copies into one burst", () => {
    const bolts = Array.from({ length: 9 }, () =>
      event("damage_dealt", { amount: 1, to: "player" }, { player: 1 }),
    );
    const plan = planCombat(bolts, SILENT, 0);
    expect(plan.leaders.size).toBe(1);
    expect(of(plan.leaders.get(0), "float")).toHaveLength(9);
  });

  /**
   * A run is closed by anything that would itself be narrated.
   *
   * Without this, "damage, a trigger resolves, more damage" would merge into
   * one burst and put the second exchange on screen before the trigger that
   * caused it.
   */
  it("does not merge two exchanges across a narrated event", () => {
    const plan = planCombat(
      [
        event("damage_dealt", { amount: 2, to: "player" }, { player: 1 }),
        event("ability_triggered", { card: "blood_artist" }),
        event("damage_dealt", { amount: 2, to: "player" }, { player: 1 }),
      ],
      SILENT,
      0,
    );
    expect([...plan.leaders.keys()]).toEqual([0, 2]);
  });

  it("keeps the prose of a lone hit and drops it for a collapsed run", () => {
    const one = planCombat(
      [event("damage_dealt", { amount: 3, to: "player" }, { player: 1 })],
      SILENT,
      0,
    );
    expect(one.wordless.has(0)).toBe(false);
    expect(planCombat(TRADE, SILENT, 0).wordless.has(3)).toBe(true);
  });

  it("finds no combat in a batch that has none", () => {
    const plan = planCombat(
      [event("draw"), event("spell_cast", { card: "sol_ring" })],
      SILENT,
      0,
    );
    expect(plan.leaders.size).toBe(0);
    expect(plan.absorbed.size).toBe(0);
  });

  it("ignores damage of zero", () => {
    const plan = planCombat(
      [event("damage_dealt", { amount: 0, to: "player" }, { player: 1 })],
      SILENT,
      0,
    );
    expect(plan.leaders.size).toBe(0);
  });
});
