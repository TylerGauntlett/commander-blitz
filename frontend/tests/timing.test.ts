/**
 * The snappiness budget.
 *
 * The board is gaining collisions, impacts and explosions, and the one thing
 * that must not happen is the game getting slower to watch. Effects are being
 * made *concurrent* rather than sequential precisely so that density can go up
 * while wall-clock does not.
 *
 * That is an easy promise to make and an easy one to break one beat at a time,
 * so it is a test instead. `BUDGET` is what each batch cost before any of this
 * work started, measured against the real `beatsFor`. A change that makes a
 * turn longer to sit through fails here.
 *
 * The assertion is `<=`, not equality: getting faster is always allowed, and a
 * choreography that merges eight queued beats into one should come in well
 * under its old number.
 */

import { describe, expect, it } from "vitest";
import type { GameEvent } from "../src/api/types";
import { beatsFor, type NameLookup, queueDuration } from "../src/logic/events";
import { SPEED_MULTIPLIER } from "../src/state/uiStore";

const NAMES = ["You", "Edgar AI"];

/** The default playback speed. `instant` bypasses the queue entirely. */
const SPEED = SPEED_MULTIPLIER.fast;

function event(
  type: string,
  data: Record<string, unknown> = {},
  extra: Partial<GameEvent> = {},
): GameEvent {
  return { type, turn: 4, step: 8, player: 0, source: null, data, ...extra };
}

/**
 * A three-attacker swing: two blocked, one through, one trade.
 *
 * The shape `logic/choreography.ts` exists to collapse. Today this is nine
 * separate holds played one after another.
 */
function combatExchange(): GameEvent[] {
  return [
    event("attackers_declared", { attackers: [11, 12, 13] }),
    event("attacks", { attacker: 11, defender: 1 }, { source: 11 }),
    event("attacks", { attacker: 12, defender: 1 }, { source: 12 }),
    event("attacks", { attacker: 13, defender: 1 }, { source: 13 }),
    event("blockers_declared", { attackers: [11, 12], blockers: [21, 22] }, { player: 1 }),
    event("blocks", { blocker: 21, attacker: 11 }, { player: 1, source: 21 }),
    event("blocks", { blocker: 22, attacker: 12 }, { player: 1, source: 22 }),
    event("became_blocked", { attacker: 11, oid: 11, blockers: 1, defender: 1 }),
    event("became_blocked", { attacker: 12, oid: 12, blockers: 1, defender: 1 }),
    event("attacked_unblocked", { attacker: 13, oid: 13, defender: 1 }),
    event(
      "damage_dealt",
      { amount: 3, to: "permanent", oid: 21, combat: true },
      { source: 11 },
    ),
    event(
      "damage_dealt",
      { amount: 2, to: "permanent", oid: 11, combat: true },
      { source: 21 },
    ),
    event(
      "damage_dealt",
      { amount: 4, to: "permanent", oid: 22, combat: true },
      { source: 12 },
    ),
    event("damage_dealt", { amount: 5, to: "player", combat: true }, { player: 1, source: 13 }),
    event("combat_damage_to_player", { amount: 5 }, { player: 1 }),
    event(
      "zone_change",
      {
        oid: 21,
        card: "grizzly_bears",
        from: "battlefield",
        to: "graveyard",
        cause: "lethal_damage",
        by: 11,
        by_card: "serra_angel",
      },
      { player: 1 },
    ),
    event(
      "zone_change",
      {
        oid: 22,
        card: "llanowar_elves",
        from: "battlefield",
        to: "graveyard",
        cause: "lethal_damage",
        by: 12,
        by_card: "shivan_dragon",
      },
      { player: 1 },
    ),
  ];
}

/** Six permanents wiped at once: the batch `exitHold` was tuned around. */
function wrath(): GameEvent[] {
  const dead = [
    [31, "grizzly_bears"],
    [32, "llanowar_elves"],
    [33, "serra_angel"],
    [34, "shivan_dragon"],
    [35, "birds_of_paradise"],
    [36, "solemn_simulacrum"],
  ] as const;
  return [
    event("spell_cast", { card: "wrath_of_god" }),
    ...dead.flatMap(([oid, card]) => [
      event("dies", { oid }, { source: oid }),
      event("leaves_battlefield", { oid }, { source: oid }),
      event("zone_change", {
        oid,
        card,
        from: "battlefield",
        to: "graveyard",
        cause: "destroyed",
        by_card: "wrath_of_god",
      }),
    ]),
    event("spell_resolved", { card: "wrath_of_god" }),
  ];
}

/** A quiet ramp turn: the common case, and the one most at risk of bloat. */
function landTurn(): GameEvent[] {
  return [
    event("turn_began", { turn: 4 }),
    event("draw", {}),
    event("land_played", { card: "forest" }, { source: 41 }),
    ...[42, 43, 44, 45].flatMap((oid) => [
      event("tapped", {}, { source: oid }),
      event("mana_added", { amount: 1 }),
    ]),
    event("mana_spent", { cost: "{4}" }),
    event("spell_cast", { card: "solemn_simulacrum" }),
    event("spell_resolved", { card: "solemn_simulacrum" }),
    event("enters_battlefield", { card: "solemn_simulacrum" }, { source: 46 }),
    event("ability_triggered", { card: "solemn_simulacrum", trigger: "etb" }, { source: 46 }),
    event("draw", {}),
  ];
}

/** Eight copies on the stack: the widest fan-out the queue ever sees. */
function stormTurn(): GameEvent[] {
  return [
    event("spell_cast", { card: "grapeshot" }),
    ...Array.from({ length: 8 }, () => event("spell_copied", { card: "grapeshot" })),
    ...Array.from({ length: 9 }, () =>
      event("damage_dealt", { amount: 1, to: "player" }, { player: 1 }),
    ),
    event("spell_resolved", { card: "grapeshot" }),
  ];
}

const BATCHES: Record<string, () => GameEvent[]> = {
  "combat exchange": combatExchange,
  wrath,
  "land turn": landTurn,
  "storm turn": stormTurn,
};

/**
 * Milliseconds each batch cost *before* the game-feel work began.
 *
 * Captured from `beatsFor` itself rather than hand-totalled, so they are the
 * real numbers and not a transcription of the `hold` values. This is the
 * contract: the board may never take longer than this to say the same thing.
 */
const BUDGET: Record<keyof typeof BATCHES, number> = {
  "combat exchange": 3300,
  wrath: 1700,
  "land turn": 3530,
  "storm turn": 5540,
};

/**
 * What it costs now, with collisions, impacts and explosions in it.
 *
 * A second, tighter assertion, and the more useful one day to day: `BUDGET`
 * only catches a regression that undoes the entire gain, whereas drifting a
 * hundred milliseconds back at a time would sail under it for a long while.
 * Raise these deliberately, and only with a reason.
 */
const ACHIEVED: Record<keyof typeof BATCHES, number> = {
  "combat exchange": 1954, // was 3300
  wrath: 1520, // was 1700
  "land turn": 2840, // was 3530
  "storm turn": 2180, // was 5540
};

const lookup: NameLookup = () => undefined;

describe("the snappiness budget", () => {
  for (const [name, build] of Object.entries(BATCHES)) {
    it(`plays a ${name} no slower than it used to`, () => {
      const beats = beatsFor(build(), NAMES, lookup, 0);
      const ms = queueDuration(beats, SPEED);
      expect(ms).toBeLessThanOrEqual(BUDGET[name]);
    });
  }

  for (const [name, build] of Object.entries(BATCHES)) {
    it(`holds a ${name} to what it costs today`, () => {
      const beats = beatsFor(build(), NAMES, lookup, 0);
      expect(queueDuration(beats, SPEED)).toBeLessThanOrEqual(ACHIEVED[name]);
    });
  }

  /**
   * The batches have to keep producing beats for the budget to mean anything.
   * A refactor that silently dropped every combat beat would otherwise pass
   * every assertion above with a duration of zero.
   */
  for (const [name, build] of Object.entries(BATCHES)) {
    it(`still animates a ${name}`, () => {
      expect(beatsFor(build(), NAMES, lookup, 0).length).toBeGreaterThan(0);
    });
  }
});
