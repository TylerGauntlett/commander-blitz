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
  /** Battlefield only. */
  damage?: number;
  tapped?: boolean;
  summoning_sick?: boolean;
  counters?: Record<string, number>;
  attached_to?: number | null;
  attacking?: boolean;
  blocking?: boolean;
}

export interface PlayerView {
  pid: number;
  name: string;
  deck_id: string;
  life: number;
  has_lost: boolean;
  loss_reason: string | null;
  lands_played: number;
  mana_pool: Record<string, number>;
  commander_tax: Record<string, number>;
  commander_damage_taken: Record<string, number>;
  library_count: number;
  hand_count: number;
  /** Null for everyone but the viewing seat. */
  hand: CardView[] | null;
  graveyard: CardView[];
  exile: CardView[];
  command: CardView[];
}

export interface DecisionOption {
  label: string;
  ref: { kind: string; id: number } | null;
  value: unknown;
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
  turn: number;
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
