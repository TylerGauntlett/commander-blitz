/**
 * Builders for the server's view types.
 *
 * These live under `src/` rather than `tests/` because `src/` is the only tree
 * the app, the unit tests and the Storybook glob all share -- a story cannot
 * reach up into `tests/`, and duplicating the builders for it would mean two
 * definitions of what a card is. Nothing in the app imports this directory, so
 * none of it reaches the bundle; `tests/imports.test.ts` holds that line.
 *
 * Every builder takes overrides and fills the rest with something plausible, so
 * a test or a story names only the field it is actually about.
 */

import type {
  CardResponse,
  CardView,
  CombatView,
  DecisionOption,
  DeckDetail,
  DeckSummary,
  GameEvent,
  GameView,
  LegalAction,
  PendingDecision,
  PlayerView,
  PodSeatView,
  PodView,
  StackItemView,
  StateResponse,
} from "../api/types";

export function card(overrides: Partial<CardView> = {}): CardView {
  return {
    oid: 1,
    card_id: "t_bear",
    name: "Test Bear",
    type_line: "Creature - Bear",
    mana_cost: "{1}{G}",
    mana_value: 2,
    colors: ["G"],
    oracle_text: "",
    controller: 0,
    owner: 0,
    zone: "battlefield",
    is_token: false,
    is_commander: false,
    power: 2,
    toughness: 2,
    types: ["Creature"],
    subtypes: ["Bear"],
    keywords: [],
    supertypes: [],
    produces: [],
    damage: 0,
    tapped: false,
    summoning_sick: false,
    counters: {},
    ...overrides,
  };
}

export function player(overrides: Partial<PlayerView> = {}): PlayerView {
  return {
    pid: 0,
    name: "You",
    deck_id: "aesi",
    life: 40,
    has_lost: false,
    loss_reason: null,
    lands_played: 0,
    land_drops_available: 1,
    mana_pool: {},
    mana: { pool: {}, sources: [], total: 0 },
    commander_tax: {},
    commander_cost: {},
    commander_damage_taken: {},
    mulligans_taken: 0,
    energy: 0,
    mulligans_free: 1,
    mulligans_max: 6,
    library_count: 60,
    library_top: null,
    library_top_public: false,
    hand_count: 0,
    hand: [],
    hand_reasons: {},
    hand_revealed: [],
    graveyard: [],
    exile: [],
    exile_hidden_count: 0,
    command: [],
    ...overrides,
  };
}

/**
 * A spell waiting to resolve.
 *
 * `oid` defaults to the face's own, because a spell on the stack *is* the object
 * it will become -- that identity is what lets a hover on the commander plinth
 * resolve to the card mid-cast.
 */
export function stackItem(overrides: Partial<StackItemView> = {}): StackItemView {
  const face = overrides.card === undefined ? card({ zone: "stack" }) : overrides.card;
  return {
    sid: 1,
    kind: "spell",
    controller: 0,
    def_id: face?.card_id ?? "t_bear",
    name: face?.name ?? "Test Bear",
    type_line: face?.type_line ?? "Creature - Bear",
    oid: face?.oid ?? null,
    source_oid: null,
    targets: [],
    description: face?.name ?? "Test Bear",
    card: face,
    ...overrides,
  };
}

/**
 * A decision waiting on somebody.
 *
 * Defaults to the one the game spends most of its time in: this seat holding
 * priority with nothing it must choose between.
 */
export function pending(overrides: Partial<PendingDecision> = {}): PendingDecision {
  return {
    kind: "priority",
    player: 0,
    prompt: "",
    options: [],
    min_count: 1,
    max_count: 1,
    selected: [],
    allow_done: true,
    context: {},
    ...overrides,
  };
}

/**
 * One choice in a prompt.
 *
 * `card` is the field worth knowing about: without it a prompt about hidden
 * cards is a row of names, because `findCard` can only search the zones the
 * player view sends and a library is a count.
 */
export function decisionOption(overrides: Partial<DecisionOption> = {}): DecisionOption {
  return {
    label: "Option",
    ref: null,
    value: null,
    ...overrides,
  };
}

/** Combat, before anything has been declared. */
export function combat(overrides: Partial<CombatView> = {}): CombatView {
  return {
    attackers: {},
    blockers: {},
    block_order: {},
    removed: [],
    attackers_declared: false,
    blockers_declared: false,
    ...overrides,
  };
}

/**
 * One entry in the event log.
 *
 * `step` is a number here and a string on `GameView` -- the event carries the
 * engine's step index, the view carries its name.
 */
export function gameEvent(overrides: Partial<GameEvent> = {}): GameEvent {
  return {
    type: "draw",
    turn: 1,
    step: 0,
    player: 0,
    source: null,
    data: {},
    ...overrides,
  };
}

export function gameView(overrides: Partial<GameView> = {}): GameView {
  return {
    seat: 0,
    turn: 1,
    round: 1,
    step: "PRECOMBAT_MAIN",
    phase: "precombat_main",
    active_player: 0,
    priority_player: 0,
    game_over: false,
    winners: [],
    result: "",
    players: [player(), player({ pid: 1, name: "AI 1", deck_id: "edgar", hand: null })],
    battlefield: [],
    stack: [],
    combat: null,
    full_control: false,
    manual_mana: false,
    pending: pending(),
    ...overrides,
  };
}

export function action(overrides: Partial<LegalAction> = {}): LegalAction {
  return {
    id: "a0-pass",
    kind: "pass",
    label: "Pass",
    base_label: "Pass",
    option_label: "",
    source_oid: null,
    ability_index: null,
    targets: [],
    choice: null,
    x: 0,
    pays: [],
    ...overrides,
  };
}

/** A whole `/api/state` response, for anything that consumes the envelope. */
export function stateResponse(overrides: Partial<StateResponse> = {}): StateResponse {
  const state = overrides.state ?? gameView();
  return {
    state,
    actions: [],
    events: [],
    event_cursor: 0,
    version: 1,
    your_seat: state.seat,
    human_seats: [0],
    ...overrides,
  };
}

/* ------------------------------------------------------------------ */
/* Decks and cards outside a game                                      */
/* ------------------------------------------------------------------ */

export function deckSummary(overrides: Partial<DeckSummary> = {}): DeckSummary {
  return {
    id: "aesi",
    name: "Aesi, Tyrant of Gyre Strait",
    commanders: ["aesi_tyrant_of_gyre_strait"],
    commander_names: ["Aesi, Tyrant of Gyre Strait"],
    color_identity: ["G", "U"],
    card_count: 100,
    notes: "Simic ramp and landfall.",
    source: "favorite",
    playable: 100,
    simplified: 0,
    tags: ["Ramp", "Landfall"],
    archetype: "",
    release: null,
    starred: false,
    ...overrides,
  };
}

/**
 * The dossier's half of a deck.
 *
 * Defaults to a favorite, since only a shipped deck has the authored half at
 * all -- an imported deck's `ratings` are null and its `strategy` empty, and the
 * screen's whole design point is that it says so. Pass those explicitly.
 */
export function deckDetail(overrides: Partial<DeckDetail> = {}): DeckDetail {
  return {
    ...deckSummary(),
    ratings: { speed: 2, complexity: 3, interaction: 2, resilience: 3, pilot: 2 },
    strategy: "The first four turns are spent almost entirely on mana.",
    signature: [
      {
        card_id: "tatyova_benthic_druid",
        name: "Tatyova, Benthic Druid",
        why: "A second Aesi.",
        art_url: "/art/tatyova_benthic_druid.jpg",
      },
    ],
    curve: [9, 13, 18, 7, 7, 3, 5],
    lands: 37,
    swaps: 5,
    swap_note: "5 cards swapped for engine-supported equivalents -- Rhystic Study.",
    ...overrides,
  };
}

/** `GET /api/cards/{id}` -- the printed card, independent of any game. */
export function cardResponse(overrides: Partial<CardResponse> = {}): CardResponse {
  return {
    id: "aesi_tyrant_of_gyre_strait",
    name: "Aesi, Tyrant of Gyre Strait",
    type_line: "Legendary Creature — Serpent",
    mana_cost: "{4}{G}{U}",
    mana_value: 6,
    oracle_text: "Trample.",
    power: 5,
    toughness: 5,
    keywords: ["Trample"],
    colors: ["G", "U"],
    color_identity: ["G", "U"],
    art_url: "/art/aesi_tyrant_of_gyre_strait.jpg",
    artist: "Jesper Ejsing",
    ...overrides,
  };
}

/* ------------------------------------------------------------------ */
/* Pods                                                                */
/* ------------------------------------------------------------------ */

export function podSeat(overrides: Partial<PodSeatView> = {}): PodSeatView {
  return {
    index: 0,
    kind: "empty",
    name: null,
    deck: null,
    locked: false,
    ready: false,
    is_you: false,
    is_host: false,
    agent: null,
    ...overrides,
  };
}

/**
 * A pod, with any seats you name and empty chairs after them.
 *
 * Seat indices are rewritten to their position, because a fixture whose seat 2
 * says `index: 0` produces bugs in the *test* rather than in the code.
 */
export function podView(
  seats: Partial<PodSeatView>[] = [],
  overrides: Partial<PodView> = {},
): PodView {
  const filled = seats.map((seat, index) => podSeat({ ...seat, index }));
  while (filled.length < 4) filled.push(podSeat({ index: filled.length }));
  const you = filled.find((seat) => seat.is_you) ?? null;
  return {
    code: "GYRE-8412",
    version: 3,
    status: "open",
    seats: filled,
    your_seat: you ? you.index : null,
    you_are_host: you ? you.is_host : false,
    game_id: null,
    invite_link: "/pods/GYRE-8412",
    ...overrides,
  };
}
