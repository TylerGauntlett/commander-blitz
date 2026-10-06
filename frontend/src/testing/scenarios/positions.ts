/** The ordinary turns of a two-seat game: a deal, a board, both halves of combat, a stack. */

import type { LegalAction } from "../../api/types";
import * as pool from "../cards";
import { action, combat, gameView, pending, stackItem } from "../fixtures";
import type { Scenario } from "./build";
import { opponent, pass, you } from "./build";

/** Turn one: seven cards, one land drop, an empty board. */
export function openingHand(): Scenario {
  const hand = [
    pool.forest({ oid: 101, zone: "hand" }),
    pool.island({ oid: 102, zone: "hand" }),
    pool.llanowarElves({ oid: 103, zone: "hand" }),
    pool.cultivate({ oid: 104, zone: "hand" }),
    pool.counterspell({ oid: 105, zone: "hand" }),
    pool.solRing({ oid: 106, zone: "hand" }),
    pool.thragtusk({ oid: 107, zone: "hand" }),
  ];

  const state = gameView({
    players: [
      you({
        hand,
        // Everything but the lands is unplayable on turn one, and each says why.
        hand_reasons: {
          103: "mana",
          104: "mana",
          105: "mana",
          106: "mana",
          107: "mana",
        },
      }),
      opponent(1, "AI 1"),
    ],
  });

  return {
    state,
    actions: [
      pass,
      action({
        id: "a1-play_land",
        kind: "play_land",
        label: "Play Forest",
        base_label: "Play Forest",
        source_oid: 101,
      }),
      action({
        id: "a2-play_land",
        kind: "play_land",
        label: "Play Island",
        base_label: "Play Island",
        source_oid: 102,
      }),
    ],
    events: [],
  };
}

/** Four lands out, real mana available, a spell that can actually be cast. */
export function earlyBoard(): Scenario {
  const battlefield = [
    pool.forest({ oid: 201 }),
    pool.forest({ oid: 202 }),
    pool.island({ oid: 203 }),
    pool.breedingPool({ oid: 204 }),
    pool.llanowarElves({ oid: 205, summoning_sick: false }),
    pool.solRing({ oid: 206 }),
  ];
  const hand = [
    pool.thragtusk({ oid: 210, zone: "hand" }),
    pool.counterspell({ oid: 211, zone: "hand" }),
    pool.rhysticStudy({ oid: 212, zone: "hand" }),
    pool.forest({ oid: 213, zone: "hand" }),
  ];

  const state = gameView({
    turn: 7,
    round: 4,
    players: [you({ hand, lands_played: 0 }, battlefield), opponent(1, "AI 1")],
    battlefield,
  });

  return {
    state,
    actions: [
      pass,
      action({
        id: "a1-cast",
        kind: "cast",
        label: "Cast Thragtusk",
        base_label: "Cast Thragtusk",
        source_oid: 210,
        // The engine's own solved payment: what the mana row highlights on hover.
        pays: [201, 202, 203, 204, 206],
      }),
      action({
        id: "a2-cast",
        kind: "cast",
        label: "Cast Rhystic Study",
        base_label: "Cast Rhystic Study",
        source_oid: 212,
        pays: [203, 204, 206],
      }),
      action({
        id: "a3-play_land",
        kind: "play_land",
        label: "Play Forest",
        base_label: "Play Forest",
        source_oid: 213,
      }),
      action({
        id: "a4-activate",
        kind: "activate",
        label: "Llanowar Elves: {T}: Add {G}",
        base_label: "Llanowar Elves: {T}: Add {G}",
        source_oid: 205,
        ability_index: 0,
      }),
    ],
    events: [],
  };
}

/**
 * Declare attackers, with two opponents.
 *
 * More than one legal defender is the case worth posing: with a single
 * opponent the panel can put the action id on the attacker, and with two it has
 * to put one on each defender chip instead. That branch is where duplicate
 * action ids have historically appeared.
 */
export function combatDeclareAttackers(): Scenario {
  const battlefield = [
    pool.llanowarElves({ oid: 301, summoning_sick: false }),
    pool.serraAngel({ oid: 302, summoning_sick: false }),
    pool.thragtusk({ oid: 303, summoning_sick: false }),
    pool.forest({ oid: 304 }),
    pool.plains({ oid: 305 }),
    pool.grizzlyBears({ oid: 350, controller: 1, owner: 1 }),
    pool.swamp({ oid: 351, controller: 1, owner: 1 }),
    pool.krakenToken({ oid: 360, controller: 2, owner: 2 }),
  ];

  const state = gameView({
    turn: 9,
    round: 5,
    step: "DECLARE_ATTACKERS",
    phase: "combat",
    players: [
      you({ hand: [pool.counterspell({ oid: 310, zone: "hand" })] }, battlefield),
      opponent(1, "AI 1"),
      opponent(2, "AI 2"),
    ],
    battlefield,
    combat: combat(),
    pending: pending({ kind: "declare_attackers", prompt: "Declare attackers" }),
  });

  // One action per (attacker, defender) pair, which is exactly the shape
  // `defendersFor` and `availableAttackers` consume.
  const attackers = [301, 302, 303];
  const defenders = [1, 2];
  const actions: LegalAction[] = [];
  for (const attacker of attackers) {
    for (const defender of defenders) {
      const name = battlefield.find((c) => c.oid === attacker)?.name ?? "";
      actions.push(
        action({
          id: `a-atk-${attacker}-${defender}`,
          kind: "add_attacker",
          label: `Attack with ${name} -> AI ${defender}`,
          base_label: `Attack with ${name}`,
          source_oid: attacker,
          targets: [{ kind: "player", id: defender }],
        }),
      );
    }
  }
  actions.push(
    action({
      id: "a-finish",
      kind: "finish_declaration",
      label: "Confirm attacks",
      base_label: "Confirm attacks",
    }),
  );

  return { state, actions, events: [] };
}

/** Declare blockers: four attackers against three blockers. */
export function combatDeclareBlockers(): Scenario {
  const battlefield = [
    pool.wallOfRoots({ oid: 401, summoning_sick: false }),
    pool.grizzlyBears({ oid: 402, summoning_sick: false }),
    pool.serraAngel({ oid: 403, summoning_sick: false }),
    pool.forest({ oid: 404 }),
    pool.krakenToken({ oid: 410, controller: 1, owner: 1, attacking: true }),
    pool.thragtusk({ oid: 411, controller: 1, owner: 1, attacking: true }),
    pool.grizzlyBears({ oid: 412, controller: 1, owner: 1, attacking: true }),
    pool.llanowarElves({ oid: 413, controller: 1, owner: 1, attacking: true }),
  ];

  const state = gameView({
    turn: 10,
    round: 5,
    step: "DECLARE_BLOCKERS",
    phase: "combat",
    active_player: 1,
    players: [you({ hand: [] }, battlefield), opponent(1, "AI 1")],
    battlefield,
    combat: combat({
      attackers: { 410: 0, 411: 0, 412: 0, 413: 0 },
      attackers_declared: true,
    }),
    pending: pending({ kind: "declare_blockers", prompt: "Declare blockers" }),
  });

  const blockers = [401, 402, 403];
  const attackers = [410, 411, 412, 413];
  const actions: LegalAction[] = [];
  for (const blocker of blockers) {
    for (const attacker of attackers) {
      const bName = battlefield.find((c) => c.oid === blocker)?.name ?? "";
      const aName = battlefield.find((c) => c.oid === attacker)?.name ?? "";
      actions.push(
        action({
          id: `a-blk-${blocker}-${attacker}`,
          kind: "add_blocker",
          label: `${bName} blocks ${aName}`,
          base_label: `${bName} blocks`,
          source_oid: blocker,
          targets: [{ kind: "object", id: attacker }],
        }),
      );
    }
  }
  actions.push(
    action({
      id: "a-finish",
      kind: "finish_declaration",
      label: "Confirm blocks",
      base_label: "Confirm blocks",
    }),
  );

  return { state, actions, events: [] };
}

/** Three deep: a creature spell, a counter aimed at it, and a trigger on top. */
export function stackThreeDeep(): Scenario {
  const battlefield = [
    pool.island({ oid: 501 }),
    pool.island({ oid: 502 }),
    pool.rhysticStudy({ oid: 503 }),
    pool.swamp({ oid: 510, controller: 1, owner: 1 }),
  ];

  const spell = pool.thragtusk({ oid: 520, zone: "stack", controller: 1, owner: 1 });
  const counter = pool.counterspell({ oid: 521, zone: "stack" });

  const state = gameView({
    turn: 8,
    round: 4,
    active_player: 1,
    players: [
      you({ hand: [pool.counterspell({ oid: 530, zone: "hand" })] }, battlefield),
      opponent(1, "AI 1"),
    ],
    battlefield,
    stack: [
      stackItem({ sid: 1, controller: 1, card: spell }),
      stackItem({
        sid: 2,
        controller: 0,
        card: counter,
        targets: [{ kind: "stack", id: 1 }],
        description: "Counterspell -> Thragtusk",
      }),
      stackItem({
        sid: 3,
        kind: "trigger",
        controller: 0,
        card: pool.rhysticStudy({ oid: 503 }),
        source_oid: 503,
        name: "Rhystic Study",
        description: "Rhystic Study: draw unless that player pays {1}",
      }),
    ],
  });

  return { state, actions: [pass], events: [] };
}
