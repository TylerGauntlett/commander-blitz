import type {
  CardView,
  GameView,
  LegalAction,
  PlayerView,
  StackItemView,
} from "../src/api/types";

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
    library_count: 60,
    hand_count: 0,
    hand: [],
    hand_reasons: {},
    graveyard: [],
    exile: [],
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
    pending: {
      kind: "priority",
      player: 0,
      prompt: "",
      options: [],
      min_count: 1,
      max_count: 1,
      selected: [],
      allow_done: true,
      context: {},
    },
    ...overrides,
  };
}

export function action(overrides: Partial<LegalAction> = {}): LegalAction {
  return {
    id: "a0-pass",
    kind: "pass",
    label: "Pass",
    source_oid: null,
    ability_index: null,
    targets: [],
    choice: null,
    x: 0,
    pays: [],
    ...overrides,
  };
}
