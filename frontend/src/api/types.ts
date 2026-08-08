/**
 * Types mirroring the server's pydantic DTOs.
 *
 * These are hand-mirrored on purpose: the client never reconstructs an action,
 * it echoes back an opaque `id`, so the surface that has to stay in sync is
 * small and mostly display-only.
 */

export type Zone =
  | "library"
  | "hand"
  | "battlefield"
  | "graveyard"
  | "exile"
  | "stack"
  | "command";

export interface CardView {
  oid: number;
  card_id: string;
  name: string;
  type_line: string;
  mana_cost: string;
  mana_value: number;
  colors: string[];
  oracle_text: string;
  controller: number;
  owner: number;
  zone: Zone;
  is_token: boolean;
  is_commander: boolean;
  power: number | null;
  toughness: number | null;
  types: string[];
  subtypes: string[];
  keywords: string[];
  /** "Basic", "Legendary". Printed, so it is the same in every zone. */
  supertypes: string[];
  /**
   * Every mana symbol this card's mana abilities could make, in WUBRG order.
   *
   * The board colours lands by this rather than by subtype: "Island" is
   * inferable, a nonbasic dual is not, and parsing `oracle_text` here would be
   * the guess `logic/mana.ts` exists to avoid. It says nothing about *amount* —
   * "Add {G} or {U}" and "Add {G}{U}" both report `["U", "G"]`. See `ManaView`.
   */
  produces: string[];
  /** Battlefield only. */
  damage?: number;
  tapped?: boolean;
  summoning_sick?: boolean;
  counters?: Record<string, number>;
  attached_to?: number | null;
  attacking?: boolean;
  blocking?: boolean;
}

/** Why a hand card has no play action right now. See engine/legality.py. */
export type UnplayableReason = "priority" | "timing" | "land_drop" | "mana" | "targets";

/** One untapped permanent that could be tapped for mana. */
export interface ManaSourceView {
  oid: number;
  /**
   * Every yield the ability could choose, each as the symbols it makes.
   * "Add {G} or {U}" is `[["G"], ["U"]]`; "Add {G}{U}" is `[["G", "U"]]`.
   * The union in `symbols` cannot tell those apart — and it is a whole mana.
   */
  options: string[][];
  /** Every symbol this source could make, in WUBRG order. */
  symbols: string[];
  /** How much mana it makes. "Add {G}{U}" is 2; "Add {G} or {U}" is 1. */
  amount: number;
}

/**
 * What a player could produce right now.
 *
 * `total` is an upper bound, not a promise: two sources that each read "{G} or
 * {U}" make two mana but never two of the same colour. Affordability comes from
 * the action list, never from arithmetic on this.
 */
export interface ManaView {
  pool: Record<string, number>;
  sources: ManaSourceView[];
  total: number;
}

export interface PlayerView {
  pid: number;
  name: string;
  deck_id: string;
  life: number;
  has_lost: boolean;
  loss_reason: string | null;
  lands_played: number;
  land_drops_available: number;
  mana_pool: Record<string, number>;
  mana: ManaView;
  /** Keyed by commander oid; the number of prior casts, not a mana amount. */
  commander_tax: Record<string, number>;
  /** Keyed by commander oid; the extra generic mana owed, already doubled. */
  commander_cost: Record<string, number>;
  commander_damage_taken: Record<string, number>;
  library_count: number;
  hand_count: number;
  /** Null for everyone but the viewing seat. */
  hand: CardView[] | null;
  /**
   * Keyed by oid, viewer only. A hand card absent from this map is playable;
   * null for other seats, whose hands are hidden anyway.
   */
  hand_reasons: Record<string, UnplayableReason> | null;
  graveyard: CardView[];
  exile: CardView[];
  command: CardView[];
}

export interface DecisionOption {
  label: string;
  ref: { kind: string; id: number } | null;
  value: unknown;
  /**
   * The face to draw for this option, sent only to the seat being asked.
   *
   * Without it a prompt about hidden cards is a row of names: `findCard` can
   * only search the zones `player_view` sends, and libraries are a count. Absent
   * on options that name no object, and on every option for any other seat.
   */
  card?: CardView | null;
}

export interface PendingDecision {
  kind: string;
  player: number;
  prompt: string;
  options: DecisionOption[];
  min_count: number;
  max_count: number;
  selected: number[];
  allow_done: boolean;
  context: Record<string, unknown>;
}

export interface StackItemView {
  sid: number;
  kind: string;
  controller: number;
  def_id: string;
  name: string;
  type_line: string;
  oid: number | null;
  source_oid: number | null;
  targets: { kind: string; id: number }[];
  description: string;
  /**
   * The face to draw for this item. For a spell it is the spell object; for a
   * triggered ability it is the permanent that produced it. Null only if the
   * object has already left the game.
   */
  card: CardView | null;
}

export interface CombatView {
  attackers: Record<string, number>;
  blockers: Record<string, number>;
  block_order: Record<string, number[]>;
  removed: number[];
  attackers_declared: boolean;
  blockers_declared: boolean;
}

export interface GameView {
  seat: number;
  /**
   * Player-turns taken. This is the rules counter — summoning sickness and the
   * turn cap read it — and in a pod it runs at the seat count per round.
   */
  turn: number;
  /** Full cycles of the table, which is what a player means by "turn". */
  round: number;
  step: string;
  phase: string;
  active_player: number;
  priority_player: number | null;
  game_over: boolean;
  winners: number[];
  result: string;
  players: PlayerView[];
  battlefield: CardView[];
  stack: StackItemView[];
  combat: CombatView | null;
  pending: PendingDecision | null;
  /** This seat stops at every priority window rather than only meaningful ones. */
  full_control: boolean;
}

export interface LegalAction {
  id: string;
  kind: string;
  label: string;
  source_oid: number | null;
  ability_index: number | null;
  targets: { kind: string; id: number }[];
  choice: number | null;
  x: number;
  /**
   * Permanents the solver would tap to pay for this — a forecast, so the mana
   * row can show what a hovered spell would eat. Sources only: `Payment` does
   * not itemise floating mana, so the pool is never claimed here.
   */
  pays: number[];
}

export interface GameEvent {
  type: string;
  turn: number;
  step: number;
  player: number | null;
  source: number | null;
  data: Record<string, unknown>;
}

export interface StateResponse {
  state: GameView;
  actions: LegalAction[];
  events: GameEvent[];
  event_cursor: number;
}

export interface GameCreated {
  game_id: string;
  your_seat: number;
  state: GameView;
  actions: LegalAction[];
}

export interface DeckSummary {
  id: string;
  name: string;
  commanders: string[];
  commander_names: string[];
  color_identity: string[];
  card_count: number;
  notes: string;
}

export interface SeatConfig {
  deck_id: string;
  kind: "human" | "ai";
  agent?: "random" | "heuristic" | "policy";
  name?: string;
}

/** `GET /api/cards/{id}` -- the printed card, independent of any game. */
export interface CardResponse {
  id: string;
  name: string;
  type_line: string;
  mana_cost: string;
  mana_value: number;
  oracle_text: string;
  power: number | null;
  toughness: number | null;
  keywords: string[];
  colors: string[];
  color_identity: string[];
}
