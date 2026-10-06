/**
 * Whole positions, not single cards.
 *
 * A macro component needs a `GameView` whose parts agree with each other.
 * `logic/actionMatch.ts` looks up an action's `source_oid` on the battlefield,
 * `logic/zoneGrouping.ts` bands permanents by controller, `logic/autoBlock.ts`
 * pairs attackers against blockers, and `PlayerOrb` reads a payment forecast
 * against the mana sources it drew. A state assembled field by field renders
 * happily and tests none of that -- the component takes every branch marked
 * "nothing here", and the story passes while showing an empty board.
 *
 * So the positions are built here, once, with their legal-action lists *derived
 * from the state* rather than written beside it. The client never constructs an
 * action -- it echoes back an opaque id -- so an action list a real engine could
 * not have sent is the one kind of fixture that quietly invalidates a story.
 */

import type {
  CardView,
  GameEvent,
  GameView,
  LegalAction,
  ManaSourceView,
  PlayerView,
} from "../api/types";
import * as pool from "./cards";
import {
  action,
  card,
  combat,
  decisionOption,
  gameEvent,
  gameView,
  pending,
  player,
  stackItem,
} from "./fixtures";

export interface Scenario {
  state: GameView;
  actions: LegalAction[];
  events: GameEvent[];
}

/* ------------------------------------------------------------------ */
/* Assembly helpers                                                    */
/* ------------------------------------------------------------------ */

/**
 * A mana source as the engine reports it.
 *
 * `options` and `symbols` are not the same fact and the orb draws both: "Add {G}
 * or {U}" is one mana with two options, "Add {G}{U}" is two mana with one.
 */
function source(oid: number, symbols: string[], amount = 1): ManaSourceView {
  return {
    oid,
    options: amount === 1 ? symbols.map((s) => [s]) : [symbols],
    symbols,
    amount,
  };
}

/** Untapped permanents that make mana, as the mana row would see them. */
function manaFrom(cards: CardView[]) {
  const sources = cards
    .filter((c) => !c.tapped && c.produces.length > 0)
    .map((c) => source(c.oid, c.produces, c.card_id === "sol_ring" ? 2 : 1));
  return {
    pool: {},
    sources,
    total: sources.reduce((sum, s) => sum + s.amount, 0),
  };
}

/** The viewer, wired so their board, hand and mana all describe each other. */
function you(overrides: Partial<PlayerView> = {}, battlefield: CardView[] = []): PlayerView {
  return player({
    pid: 0,
    name: "You",
    mana: manaFrom(battlefield.filter((c) => c.controller === 0)),
    hand_count: overrides.hand?.length ?? 0,
    library_count: 92,
    command: [pool.aesi({ oid: 900 })],
    ...overrides,
  });
}

/** An opponent: hand hidden, reasons null, as the server sends every other seat. */
function opponent(pid: number, name: string, overrides: Partial<PlayerView> = {}): PlayerView {
  return player({
    pid,
    name,
    deck_id: "edgar",
    hand: null,
    hand_reasons: null,
    hand_count: 7,
    library_count: 92,
    command: [pool.edgarMarkov({ oid: 900 + pid })],
    ...overrides,
  });
}

/** The action every priority window has, and the one the slab promotes. */
const pass = action({ id: "a0-pass", kind: "pass", label: "Pass", base_label: "Pass" });

/* ------------------------------------------------------------------ */
/* Positions                                                           */
/* ------------------------------------------------------------------ */

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

/** Four seats. `opponentCardScale(3)` is the legibility floor in cardSize.ts. */
export function fourPlayerPod(): Scenario {
  const battlefield = [
    pool.forest({ oid: 601 }),
    pool.island({ oid: 602 }),
    pool.thragtusk({ oid: 603, summoning_sick: false }),
    pool.swamp({ oid: 610, controller: 1, owner: 1 }),
    pool.grizzlyBears({ oid: 611, controller: 1, owner: 1 }),
    pool.mountain({ oid: 620, controller: 2, owner: 2 }),
    pool.krakenToken({ oid: 621, controller: 2, owner: 2 }),
    pool.plains({ oid: 630, controller: 3, owner: 3 }),
    pool.serraAngel({ oid: 631, controller: 3, owner: 3 }),
  ];

  const state = gameView({
    turn: 13,
    round: 4,
    players: [
      you({ hand: [pool.cultivate({ oid: 640, zone: "hand" })] }, battlefield),
      opponent(1, "AI 1"),
      opponent(2, "AI 2", { life: 28 }),
      opponent(3, "AI 3", { life: 12 }),
    ],
    battlefield,
  });

  return { state, actions: [pass], events: [] };
}

/**
 * Twenty permanents, twelve of them basics.
 *
 * Duplicates collapse into counted piles, so this is the position that exercises
 * `stackCards` grouping and the crowded branch of the zoom solver at once.
 */
export function crowdedBoard(): Scenario {
  const battlefield: CardView[] = [];
  let oid = 700;
  for (let i = 0; i < 7; i += 1) battlefield.push(pool.forest({ oid: oid++ }));
  for (let i = 0; i < 5; i += 1) battlefield.push(pool.island({ oid: oid++ }));
  for (let i = 0; i < 4; i += 1)
    battlefield.push(pool.krakenToken({ oid: oid++, summoning_sick: false }));
  battlefield.push(pool.thragtusk({ oid: oid++, summoning_sick: false }));
  battlefield.push(pool.serraAngel({ oid: oid++, summoning_sick: false }));
  battlefield.push(pool.solRing({ oid: oid++ }));
  battlefield.push(pool.rhysticStudy({ oid: oid++ }));

  const state = gameView({
    turn: 21,
    round: 11,
    players: [you({ hand: [] }, battlefield), opponent(1, "AI 1")],
    battlefield,
  });

  return { state, actions: [pass], events: [] };
}

/**
 * Four distinct artifacts and enchantments in a four-player pod.
 *
 * The Steam Deck playtest board: the global lane is a third of the front band,
 * two cards wide at handheld size, so the third card used to start a second
 * row and push the lands and the viewer's own seat off the screen. Distinct
 * cards on purpose -- duplicates collapse into one counted pile and would not
 * crowd the lane at all.
 */
export function fullGlobalLane(): Scenario {
  const battlefield = [
    pool.thragtusk({ oid: 1101, summoning_sick: false }),
    pool.serraAngel({ oid: 1102, summoning_sick: false }),
    pool.grizzlyBears({ oid: 1103, summoning_sick: false }),
    pool.solRing({ oid: 1104 }),
    pool.mindStone({ oid: 1105 }),
    pool.mindStone({ oid: 1106, card_id: "arcane_signet", name: "Arcane Signet" }),
    pool.rhysticStudy({ oid: 1107 }),
    pool.plains({ oid: 1108 }),
    pool.swamp({ oid: 1110, controller: 1, owner: 1 }),
    pool.mountain({ oid: 1120, controller: 2, owner: 2 }),
    pool.island({ oid: 1130, controller: 3, owner: 3 }),
  ];

  const state = gameView({
    turn: 5,
    round: 5,
    players: [
      you({ hand: [pool.cultivate({ oid: 1140, zone: "hand" })] }, battlefield),
      opponent(1, "AI 1"),
      opponent(2, "AI 2"),
      opponent(3, "AI 3"),
    ],
    battlefield,
  });

  return { state, actions: [pass], events: [] };
}

/** A creature wearing an Aura and an Equipment: the tucked-attachment path. */
export function withAttachments(): Scenario {
  const host = pool.serraAngel({ oid: 801, summoning_sick: false });
  const battlefield = [
    host,
    pool.rancor({ oid: 802, attached_to: 801 }),
    pool.swordOfFireAndIce({ oid: 803, attached_to: 801 }),
    pool.plains({ oid: 804 }),
  ];

  const state = gameView({
    players: [you({ hand: [] }, battlefield), opponent(1, "AI 1")],
    battlefield,
  });

  return { state, actions: [pass], events: [] };
}

/** Graveyard, exile and command all populated, so the zone viewer has content. */
export function fullZones(): Scenario {
  const battlefield = [pool.forest({ oid: 851 }), pool.island({ oid: 852 })];
  const state = gameView({
    turn: 15,
    round: 8,
    players: [
      you(
        {
          hand: [pool.counterspell({ oid: 860, zone: "hand" })],
          graveyard: [
            pool.grizzlyBears({ oid: 870, zone: "graveyard" }),
            pool.forest({ oid: 871, zone: "graveyard" }),
            pool.forest({ oid: 872, zone: "graveyard" }),
            pool.cultivate({ oid: 873, zone: "graveyard" }),
          ],
          exile: [pool.thragtusk({ oid: 880, zone: "exile" })],
        },
        battlefield,
      ),
      opponent(1, "AI 1"),
    ],
    battlefield,
  });

  return { state, actions: [pass], events: [] };
}

/** Somebody won. `winners: [0]` is the viewer, so this is the victory face. */
export function gameOver(winner = 0): Scenario {
  const state = gameView({
    turn: 30,
    round: 15,
    game_over: true,
    winners: [winner],
    result: winner === 0 ? "You win" : "AI 1 wins",
    pending: null,
    players: [
      you({ hand: [], life: winner === 0 ? 22 : 0, has_lost: winner !== 0 }),
      opponent(1, "AI 1", {
        life: winner === 1 ? 18 : 0,
        has_lost: winner !== 1,
        loss_reason: winner !== 1 ? "life" : null,
      }),
    ],
  });

  return { state, actions: [], events: [] };
}

/* ------------------------------------------------------------------ */
/* Modal decisions                                                     */
/* ------------------------------------------------------------------ */

/** The seven the opening-hand scenarios below all deal. */
function openingSeven() {
  return [
    pool.forest({ oid: 101, zone: "hand" }),
    pool.forest({ oid: 102, zone: "hand" }),
    pool.forest({ oid: 103, zone: "hand" }),
    pool.thragtusk({ oid: 104, zone: "hand" }),
    pool.serraAngel({ oid: 105, zone: "hand" }),
    pool.cultivate({ oid: 106, zone: "hand" }),
    pool.counterspell({ oid: 107, zone: "hand" }),
  ];
}

/**
 * The first half of a London mulligan: keep this hand, or take another seven.
 *
 * NEITHER OPTION CARRIES A CARD, and the comment that used to sit here claimed
 * the opposite. `engine/game.py` builds these two as bare
 * `DecisionOption(label=..., value=...)` with no `ref`, so `serialize._pending`
 * attaches no face and `PromptDialog.rowsFor` finds none -- which is exactly why
 * the one decision whose whole subject is a set of cards used to render as two
 * grey rectangles. `OpeningHand` does not read the options at all; it draws
 * `players[seat].hand`, which the server sends in full to the seat being asked.
 */
export function mulligan(taken = 0): Scenario {
  const hand = openingSeven();

  const state = gameView({
    step: "UNTAP",
    phase: "beginning",
    players: [{ ...you({ hand }), mulligans_taken: taken }, opponent(1, "AI 1")],
    pending: pending({ kind: "mulligan", prompt: "Keep this hand?" }),
  });

  return {
    state,
    actions: [
      action({ id: "a0-keep", kind: "keep", label: "Keep", base_label: "Keep" }),
      action({
        id: "a1-mulligan",
        kind: "mulligan",
        label: "Mulligan",
        base_label: "Mulligan",
      }),
    ],
    events: [],
  };
}

/**
 * The second half: two mulligans taken, the first free, so one card goes to
 * the bottom.
 *
 * A different decision KIND from the first half -- `choose_objects`, raised by
 * `ask_objects` -- and the only thing that tells it apart from every other
 * `choose_objects` is the `purpose` tag the engine stamps on it. That tag is why
 * `logic/openingHand.ts` never has to read the prompt string, and matching the
 * real payload here is the point of the fixture: these options DO carry refs and
 * faces, where the first half's carry neither.
 *
 * `bottom` is `min_count`, and the lamps show one more than that taken: a
 * London mulligan bottoms one card per mulligan, less the free one
 * (`FREE_MULLIGANS` in `engine/game.py`). `selected` is what the engine
 * has already banked, which is the half of this decision a single pick cannot
 * show: on two, the screen has to say how many are still wanted.
 */
export function mulliganBottom(bottom = 1, selected: number[] = []): Scenario {
  const hand = openingSeven();
  const state = gameView({
    step: "UNTAP",
    phase: "beginning",
    players: [
      { ...you({ hand }), mulligans_taken: bottom + 1 },
      { ...opponent(1, "AI 1"), mulligans_taken: 0 },
    ],
    pending: pending({
      kind: "choose_objects",
      prompt: `Put ${bottom} card(s) on the bottom of your library`,
      min_count: bottom,
      max_count: bottom,
      options: hand.map((c) => ({
        label: c.name,
        ref: { kind: "object", id: c.oid },
        value: c.oid,
        card: c,
      })),
      selected,
      context: { purpose: "mulligan_bottom", source_name: "Mulligan" },
    }),
  });

  return {
    state,
    /* Derived from the state, per this file's header: one action per option, in
       the same order, carrying the index the engine answers by. */
    actions: hand.map((c, i) =>
      action({
        id: `a${i}-bottom`,
        kind: "choose",
        label: c.name,
        base_label: c.name,
        choice: i,
        targets: [{ kind: "object", id: c.oid }],
      }),
    ),
    events: [],
  };
}

/** Over hand size at cleanup: choose two to pitch. */
export function discardToHandSize(): Scenario {
  const hand = [
    pool.forest({ oid: 101, zone: "hand" }),
    pool.island({ oid: 102, zone: "hand" }),
    pool.thragtusk({ oid: 103, zone: "hand" }),
    pool.serraAngel({ oid: 104, zone: "hand" }),
    pool.cultivate({ oid: 105, zone: "hand" }),
    pool.counterspell({ oid: 106, zone: "hand" }),
    pool.solRing({ oid: 107, zone: "hand" }),
    pool.rhysticStudy({ oid: 108, zone: "hand" }),
    pool.rancor({ oid: 109, zone: "hand" }),
  ];

  const state = gameView({
    step: "CLEANUP",
    phase: "ending",
    players: [you({ hand }), opponent(1, "AI 1")],
    pending: pending({
      kind: "discard_to_hand_size",
      prompt: "Discard down to seven cards",
      min_count: 2,
      max_count: 2,
    }),
  });

  return {
    state,
    actions: hand.map((c, i) =>
      action({
        id: `a${i}-choose`,
        kind: "choose",
        label: c.name,
        base_label: c.name,
        targets: [{ kind: "object", id: c.oid }],
      }),
    ),
    events: [],
  };
}

/** Choosing a permanent: options that name real objects draw as real cards. */
export function chooseTarget(): Scenario {
  const battlefield = [
    pool.grizzlyBears({ oid: 901 }),
    pool.serraAngel({ oid: 902 }),
    pool.wallOfRoots({ oid: 903 }),
  ];

  const state = gameView({
    players: [you({ hand: [] }, battlefield), opponent(1, "AI 1")],
    battlefield,
    pending: pending({ kind: "choose_objects", prompt: "Sacrifice a creature" }),
  });

  return {
    state,
    actions: battlefield.map((c, i) =>
      action({
        id: `a${i}-choose`,
        kind: "choose",
        label: c.name,
        base_label: c.name,
        targets: [{ kind: "object", id: c.oid }],
      }),
    ),
    events: [],
  };
}

/**
 * "Exile up to two target artifacts and/or enchantments" -- Angel of the Ruins.
 *
 * Both sides of the table, in the engine's order (an opponent's first), so the
 * dialog has to put yours back in front. `Done` is legal because "up to"
 * allows none.
 */
export function chooseSeveralTargets(): Scenario {
  const battlefield = [
    pool.rhysticStudy({ oid: 811, controller: 1, owner: 1 }),
    pool.solRing({ oid: 801 }),
    pool.solRing({ oid: 812, controller: 1, owner: 1 }),
    pool.rhysticStudy({ oid: 802 }),
  ];
  const options = battlefield.map((c, i) =>
    decisionOption({ label: c.name, ref: { kind: "object", id: c.oid }, value: i }),
  );

  const state = gameView({
    players: [you({ hand: [] }, battlefield), opponent(1, "AI 1")],
    battlefield,
    pending: pending({
      kind: "choose_objects",
      prompt:
        "Choose targets for Angel of the Ruins: When this creature enters, exile up to two target artifacts and/or enchantments.",
      options,
      min_count: 0,
      max_count: 2,
      context: { purpose: "target", source_name: "Angel of the Ruins" },
    }),
  });

  return {
    state,
    actions: [
      ...battlefield.map((c, i) =>
        action({
          id: `a${i}-choose`,
          kind: "choose",
          label: c.name,
          base_label: c.name,
          choice: i,
          targets: [{ kind: "object", id: c.oid }],
        }),
      ),
      action({
        id: "a4-finish_declaration",
        kind: "finish_declaration",
        label: "Done",
        base_label: "Done",
      }),
    ],
    events: [],
  };
}

/** A modal spell: three modes, no targets yet. */
export function chooseMode(): Scenario {
  const state = gameView({
    players: [you({ hand: [pool.simicCharm({ oid: 950, zone: "hand" })] })],
    pending: pending({ kind: "choose_mode", prompt: "Choose one —" }),
  });

  return {
    state,
    actions: [
      action({
        id: "a0-choose",
        kind: "choose",
        label: "Target creature gets +3/+3 until end of turn",
        base_label: "Target creature gets +3/+3 until end of turn",
        choice: 0,
      }),
      action({
        id: "a1-choose",
        kind: "choose",
        label: "Return target creature to its owner's hand",
        base_label: "Return target creature to its owner's hand",
        choice: 1,
      }),
      action({
        id: "a2-choose",
        kind: "choose",
        label: "Target creature you control gains hexproof until end of turn",
        base_label: "Target creature you control gains hexproof until end of turn",
        choice: 2,
      }),
    ],
    events: [],
  };
}

/**
 * Herald's Horn: choose a creature type, from every type in the pool.
 *
 * The real list, lifted out of `data/cards/` rather than invented -- 199 of
 * them here and up to `MAX_TYPE_CHOICES` (400) in a full pool. The engine sends
 * this as an ordinary `choose_mode` with one option per type, which is exactly
 * why the client decides on the *shape* of a decision rather than its kind: no
 * discriminator distinguishes this from a three-mode charm.
 */
export const CREATURE_TYPES = `
  Advisor Aetherborn Alien Ally Andorian Angel Antelope Ape Archer Artificer Assassin
  Astartes Avatar Badger Barbarian Basilisk Bat Bear Beast Berserker Bird Boar Caitian
  Camel Cat Centaur Chimera Citizen Cleric Cockatrice Construct Crab Crocodile Cyclops
  Dauthi Demon Devil Dinosaur Djinn Doctor Dog Dragon Drake Drone Druid Dryad Dwarf Efreet
  Elder Eldrazi Elemental Elephant Elf Elk Faerie Fish Forest Fox Frog Fungus Gamma
  Gargoyle Giant Gnome Goat Goblin God Golem Gorgon Gorn Gremlin Griffin Hag Harpy Hero
  Hippo Hippogriff Homunculus Horror Horse Human Hydra Hyena Illusion Imp Insect Jackal
  Jellyfish Kavu Kirin Kithkin Klingon Knight Kobold Kor Kraken Kree Lammasu Leech Lemur
  Leviathan Lizard Mercenary Merfolk Minion Minotaur Mole Mongoose Monk Monkey Moonfolk
  Mutant Myr Mystic Nightmare Nightstalker Ninja Noble Nomad Nymph Octopus Officer Ogre
  Ooze Orc Orgg Otter Ox Pangolin Peasant Pegasus Performer Phyrexian Pilot Pirate Plant
  Praetor Rabbit Ranger Rat Rebel Rhino Robot Rogue Sable Salamander Saproling Satyr
  Scarecrow Scientist Scorpion Scout Seal Serpent Shaman Shapeshifter Shark Sheep Siren
  Skeleton Sliver Sloth Slug Snake Soldier Soltari Sorcerer Sphinx Spider Spirit Spy
  Squirrel Surrakar Symbiote Thalakos Thopter Thrull Treefolk Troll Turtle Tyranid Unicorn
  Vampire Vedalken Villain Vulcan Wall Walrus Warlock Warrior Weasel Werewolf Whale Wizard
  Wolf Wraith Wurm Yeti Zombie
`
  .trim()
  .split(/\s+/);

export function chooseType(): Scenario {
  const state = gameView({
    players: [you({ hand: [] })],
    pending: pending({
      kind: "choose_mode",
      prompt: "Choose a creature type",
      options: CREATURE_TYPES.map((label, i) => decisionOption({ label, value: i })),
      context: { source: 960, source_name: "Herald's Horn" },
    }),
  });

  return {
    state,
    actions: CREATURE_TYPES.map((label, i) =>
      action({ id: `a${i}-choose`, kind: "choose", label, base_label: label, choice: i }),
    ),
    events: [],
  };
}

/** Pointing at a player rather than a permanent. */
export function choosePlayer(): Scenario {
  const state = gameView({
    players: [you({ hand: [] }), opponent(1, "AI 1"), opponent(2, "AI 2")],
    pending: pending({ kind: "choose_player", prompt: "Choose an opponent" }),
  });

  return {
    state,
    actions: [1, 2].map((pid) =>
      action({
        id: `a${pid}-choose`,
        kind: "choose",
        label: `AI ${pid}`,
        base_label: `AI ${pid}`,
        targets: [{ kind: "player", id: pid }],
      }),
    ),
    events: [],
  };
}

/** An optional trigger: yes or no. */
export function mayAbility(): Scenario {
  const state = gameView({
    players: [you({ hand: [] })],
    pending: pending({ kind: "may", prompt: "Draw a card unless that player pays {1}?" }),
  });

  return {
    state,
    actions: [
      action({ id: "a0-choose", kind: "choose", label: "Yes", base_label: "Yes" }),
      action({ id: "a1-choose", kind: "choose", label: "No", base_label: "No" }),
    ],
    events: [],
  };
}

/**
 * Searching a library.
 *
 * The options carry faces the player view cannot supply -- a library is a count
 * -- which is exactly what `DecisionOption.card` exists for.
 */
export function searchLibrary(): Scenario {
  const found = [
    pool.forest({ oid: 981, zone: "library" }),
    pool.island({ oid: 982, zone: "library" }),
    pool.breedingPool({ oid: 983, zone: "library" }),
  ];

  const state = gameView({
    players: [you({ hand: [] })],
    pending: pending({
      kind: "choose_objects",
      prompt: "Search your library for a basic land card",
      options: found.map((c) => ({
        label: c.name,
        ref: { kind: "object", id: c.oid },
        value: c.oid,
        card: c,
      })),
    }),
  });

  return {
    state,
    actions: found.map((c, i) =>
      action({
        id: `a${i}-choose`,
        kind: "choose",
        label: c.name,
        base_label: c.name,
        // `choice` is the index into `pending.options`, and it is what makes the
        // attached face reachable: the dialog looks the option up by it, then
        // falls back to `findCard`, which cannot resolve a library card because
        // the player view sends libraries as a count. Without this the prompt
        // renders exactly the row of bare names `option.card` was added to fix.
        choice: i,
        targets: [{ kind: "object", id: c.oid }],
      }),
    ),
    events: [],
  };
}

/**
 * One card, several ways to aim it.
 *
 * The engine emits one action per legal target tuple, so six ways to point a
 * Simic Charm arrive as six actions with one `base_label`. Grouping them into a
 * single row with a chip per target is what stops the panel reading as six
 * copies of the same card.
 */
export function targetVariants(): Scenario {
  const battlefield = [
    pool.grizzlyBears({ oid: 991 }),
    pool.krakenToken({ oid: 992 }),
    pool.wallOfRoots({ oid: 993 }),
  ];
  const charm = pool.simicCharm({ oid: 990, zone: "hand" });

  const state = gameView({
    players: [you({ hand: [charm] }, battlefield), opponent(1, "AI 1")],
    battlefield,
  });

  return {
    state,
    actions: [
      pass,
      ...battlefield.map((c) =>
        action({
          id: `a-charm-${c.oid}`,
          kind: "cast",
          label: `Cast Simic Charm -> ${c.name}`,
          base_label: "Cast Simic Charm",
          source_oid: 990,
          targets: [{ kind: "object", id: c.oid }],
        }),
      ),
    ],
    events: [],
  };
}

/**
 * A permanent offering two abilities, neither of them targeted.
 *
 * The counterpart to `targetVariants`: there the ambiguity is *which target*,
 * here it is *which ability*, and the board has nothing to point at either way.
 * Clicking the artifact must therefore reach the panel rather than resolving to
 * an action -- one of these two sacrifices it.
 */
export function twoAbilityPermanent(): Scenario {
  const battlefield = [
    pool.mindStone({ oid: 401 }),
    pool.forest({ oid: 402 }),
    pool.island({ oid: 403 }),
  ];

  const state = gameView({
    players: [you({ hand: [] }, battlefield), opponent(1, "AI 1")],
    battlefield,
  });

  return {
    state,
    actions: [
      pass,
      action({
        id: "a1-activate",
        kind: "activate",
        label: "Mind Stone: {T}: Add {C}",
        base_label: "Mind Stone: {T}: Add {C}",
        source_oid: 401,
        ability_index: 0,
      }),
      action({
        id: "a2-activate",
        kind: "activate",
        label: "Mind Stone: {1}, {T}, Sacrifice this artifact: Draw a card.",
        base_label: "Mind Stone: {1}, {T}, Sacrifice this artifact: Draw a card.",
        source_oid: 401,
        ability_index: 1,
      }),
    ],
    events: [],
  };
}

/* ------------------------------------------------------------------ */
/* Events, for the log and the FX layer                                */
/* ------------------------------------------------------------------ */

/**
 * A turn's worth of log, covering the event kinds that render differently.
 *
 * The card id goes in `data.card` -- that is what the engine emits
 * (`state.emit(..., card=card.id)`) and what `describeEvent` and `beatsFor` both
 * read. `data.card_id` is the plausible-looking spelling, and it degrades into
 * "casts a spell" on every line: grammatical, unremarkable, and wrong.
 */
export function mixedLog(): GameEvent[] {
  return [
    gameEvent({ type: "turn_began", player: 0, data: { round: 4, turn: 7 } }),
    gameEvent({ type: "land_played", player: 0, data: { card: "forest" } }),
    gameEvent({ type: "spell_cast", player: 0, data: { card: "thragtusk" } }),
    gameEvent({ type: "spell_countered", player: 1, data: { card: "thragtusk" } }),
    gameEvent({ type: "enters_battlefield", player: 1, data: { card: "grizzly_bears" } }),
    gameEvent({ type: "ability_triggered", player: 0, data: { card: "rhystic_study" } }),
    // A death is two events, always: `move_object` emits the zone change and
    // fires `dies` together. The zone change is the one that carries the words
    // now, so a fixture with a bare `dies` would silently lose its line.
    gameEvent({
      type: "zone_change",
      player: 1,
      data: {
        card: "grizzly_bears",
        oid: 350,
        from: "battlefield",
        to: "graveyard",
        cause: "destroyed",
        by: 12,
        by_card: "swords_to_plowshares",
      },
    }),
    gameEvent({ type: "dies", player: 1, data: { card: "grizzly_bears" } }),
    gameEvent({ type: "token_created", player: 0, data: { card: "kraken_token" } }),
  ];
}

/** A card that exists nowhere the view can see, for the "unknown" branches. */
export function ghostCard(): CardView {
  return card({ oid: -1, card_id: "unknown_card", name: "Unknown Card" });
}
