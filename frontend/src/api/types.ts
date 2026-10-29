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
  /**
   * A Class's level (rule 716), on the battlefield and only for a card that
   * prints level lines. Not a counter, so never inside `counters`.
   */
  level?: number;
  attached_to?: number | null;
  attacking?: boolean;
  blocking?: boolean;
  /**
   * Only on an entry of `PlayerView.commanders_unseen`: the commander is phased
   * out (Oubliette). `zone` still says battlefield, which is true and useless.
   */
  phased_out?: boolean;
}

/** Why a hand card has no play action right now. See engine/legality.py. */
export type UnplayableReason = "priority" | "timing" | "land_drop" | "mana" | "targets";

/** One untapped permanent that could be tapped for mana. */
/** One untapped permanent that can be tapped for mana. */
export interface ManaSourceView {
  oid: number;
  /**
   * Every yield the permanent could choose, each as the symbols it makes.
   * "Add {G} or {U}" is `[["G"], ["U"]]`; "Add {G}{U}" is `[["G", "U"]]`.
   * The union in `symbols` cannot tell those apart — and it is a whole mana.
   * A permanent with two tap abilities lists the options of both: a Talisman
   * is `[["C"], ["B"], ["R"]]`, still one mana.
   */
  options: string[][];
  /** Every symbol this source could make, in WUBRG order. */
  symbols: string[];
  /** How much mana one tap makes. "Add {G}{U}" is 2; "Add {G} or {U}" is 1. */
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
  /**
   * Keyed by the **player** who dealt it, not by their commander's oid.
   *
   * The odd one out: the two fields above are keyed by commander oid, and this
   * one is not -- the engine writes `taken[src.controller]`
   * (`engine/primitives.py`), because 21 damage is lethal per *opponent* and a
   * partner pair's two commanders share one total. `PlayerOrb` reads it by pid
   * to label the chips, and a fixture keyed by oid silently reports zero.
   */
  commander_damage_taken: Record<string, number>;
  /**
   * How many mulligans this seat has taken, for every seat.
   *
   * Public at a real table, and public here. `OpeningHand` draws the viewer's
   * as the lamps that say how many are left; the engine also writes it into the
   * mulligan decision's own prompt string, which is the fallback nobody should
   * have to parse.
   */
  mulligans_taken: number;
  /** Energy counters (107.14). Public; `EnergyChip` draws it while above zero. */
  energy: number;
  /** Mulligans that cost no card (`FREE_MULLIGANS` in `engine/game.py`). */
  mulligans_free: number;
  /** Most mulligans before the keep is forced (`MAX_MULLIGANS`). */
  mulligans_max: number;
  library_count: number;
  /**
   * The top card of this player's library, if this seat may see it at all.
   *
   * Null unless something on the battlefield shows it, so there is no separate
   * flag to check before drawing one. Two statics put a card here and they
   * differ in *who* gets it:
   *
   * - "Play with the top card of your library revealed" (Vampire Nocturnus) is
   *   public, so the server sends it to **every** seat -- an opponent who
   *   cannot see a revealed card is playing against information they are
   *   entitled to.
   * - "You may look at the top card of your library any time" (Verge Rangers)
   *   shows the card to nobody else, so the server sends it to that player's
   *   own seat and no other.
   */
  library_top: CardView | null;
  /**
   * Whether the card in `library_top` is public -- revealed to the whole table
   * rather than looked at privately.
   *
   * The two cases arrive as an identical payload, so without this the UI cannot
   * word them apart, and calling a private look "revealed" tells its own player
   * that the opponent shares the knowledge. False whenever `library_top` is
   * null, so it never carries a stale claim about a card that was not sent.
   */
  library_top_public: boolean;
  hand_count: number;
  /** Null for everyone but the viewing seat. */
  hand: CardView[] | null;
  /**
   * Cards in this player's hand that the viewing seat has been *shown* -- by
   * "look at target player's hand" and nothing else. Private information, so
   * the server only puts a card here for the one seat entitled to it; this is
   * what separates looking from revealing, which is public. Always empty for
   * your own hand, which `hand` sends in full.
   */
  hand_revealed: CardView[];
  /**
   * Keyed by oid, viewer only. A hand card absent from this map is playable;
   * null for other seats, whose hands are hidden anyway.
   */
  hand_reasons: Record<string, UnplayableReason> | null;
  graveyard: CardView[];
  /**
   * Exile is a public zone and arrives in full -- minus any card put there
   * *face down* (Necropotence), which the server drops for every seat not
   * entitled to see it rather than sending a half-filled `CardView`.
   */
  exile: CardView[];
  /**
   * How many face-down cards are in this player's exile that the viewing seat
   * may not see. The pile is public even when its faces are not, so zone counts
   * are `exile.length + exile_hidden_count`; `exile` alone under-counts and the
   * pile would vanish from the board on a seat that cannot see into it.
   */
  exile_hidden_count: number;
  command: CardView[];
  /**
   * This player's commanders that are in none of the zones above: phased out,
   * or in their hand or library. Sent to every seat, because a commander's
   * identity is public, and it is what keeps the seat's portrait on screen.
   * See `commandersOf`. Optional only so older fixtures still type-check.
   */
  commanders_unseen?: CardView[];
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
  /** This seat taps its own lands rather than letting the solver choose. */
  manual_mana: boolean;
}

export interface LegalAction {
  id: string;
  kind: string;
  label: string;
  /**
   * `label` without its `-> target` suffix: what this action *is*, rather than
   * which of its legal targets this copy aims at. The engine emits one action
   * per legal target tuple, so grouping the list by this is what turns "six
   * ways to aim one Simic Charm" back into one row. Never empty — the server
   * falls back to `label` for the kinds that never name a target.
   */
  base_label: string;
  /**
   * What this copy's chip says when a row groups several actions that differ by
   * something other than their target — "{R}" for one yield of "Add one mana of
   * any colour". Empty means "name it by its target", which is the usual case.
   */
  option_label: string;
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
  /**
   * For an action that names targets: oid -> why that permanent cannot be
   * named by this spell or ability at all ("Hexproof", "Shroud", "Protection
   * from red"). Display only; see `logic/targetHint.ts`.
   */
  untargetable?: Record<string, string>;
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
  /** The session's mutation counter. Fed back as `?since_version=` to long-poll. */
  version: number;
  /**
   * The seat this view is for. Echoed back because a client arriving from a pod
   * does not know it: the lobby's four chairs compact down to the players who
   * are actually in the game, so lobby seat 2 can be table seat 1.
   */
  your_seat: number;
  /**
   * Which seats are people.
   *
   * The engine does not model this -- a seat is a seat to it -- but the
   * client's behaviour turns on it: waiting for an AI means pumping it forward
   * a decision at a time, waiting for a human means long-polling until they
   * move.
   */
  human_seats: number[];
}

export interface GameCreated {
  game_id: string;
  your_seat: number;
  state: GameView;
  actions: LegalAction[];
  version: number;
}

/** Where a deck came from (ADR 0024). */
export type DeckSourceKind = "precon" | "favorite" | "moxfield";

/** The product a precon is. Mirrors `ReleaseDTO`. */
export interface DeckRelease {
  set_code: string;
  set_name: string;
  /** ISO date, so it orders as a string. */
  date: string;
}

/** A shell's commander: its printed name, and its art when a printing is known. */
export interface ShellCommander {
  name: string;
  /** `/art/<id>.jpg`, or `null` when no printing is known and the shell draws a plain plate. */
  art_url: string | null;
}

/**
 * A precon the shelf names but cannot deal yet: one from the release window
 * that is not a shipped deck. Mirrors the rows of `GET /api/precons/upcoming`,
 * which answers newest first. It is drawn as a "Coming soon" shell, never as a
 * control.
 */
export interface UpcomingPrecon {
  id: string;
  /** The product's own name, e.g. "Calling All Angels". */
  product: string;
  set_code: string;
  /** The release it belongs to; the shelf groups it with that set's decks. */
  set_name: string;
  /** ISO date, so it orders as a string. */
  date: string;
  /** Who leads it, for the shell's caption and its grayed-out art. */
  commanders: ShellCommander[];
}

export interface DeckSummary {
  id: string;
  name: string;
  commanders: string[];
  commander_names: string[];
  color_identity: string[];
  card_count: number;
  notes: string;
  /**
   * ADR 0024: "precon" is a list Wizards sold, "favorite" one the maintainer
   * ships, "moxfield" the player's own import.
   */
  source: DeckSourceKind;
  /** Cards whose printed text the engine represents in full. */
  playable: number;
  /** Cards whose non-keyword rules text does nothing. */
  simplified: number;
  /** Editorial. Empty for an imported deck, which the catalogue draws honestly. */
  tags: string[];
  /** The `ARCHETYPES` key the deck file names, or `""` when it names none. */
  archetype: string;
  /** The product a precon is, which the shelf groups by; `null` otherwise. */
  release: DeckRelease | null;
  /** The player's star on their own import. Always false on a shipped deck. */
  starred: boolean;
  /**
   * The Moxfield public id an import came from, case preserved. Empty for a
   * precon. What the desktop sends the hosted server so an imported deck can
   * follow its owner online.
   */
  source_id?: string;
  /**
   * `false` when this machine is still missing illustrations the deck can have,
   * so it would play with blank plates offline. Only the desktop build sets
   * it; `null` or absent means nobody checked.
   */
  complete?: boolean | null;
  /**
   * The deck's chosen printing of its lead commander -- a whole ref, so its
   * artist is the deck's own. `null` or absent when it chose none, and the
   * lobby draws the catalog's art.
   */
  commander_art?: { card_id: string; art: string | null; artist: string | null } | null;
}

/**
 * Which server answered, and whether the other kind is reachable.
 *
 * `GET /api/config`. The client's one source for "am I the desktop build" and
 * "can I play online right now" -- never its origin, because a desktop that
 * has lost its connection is still on `127.0.0.1` and still cannot join a pod.
 */
export interface AppConfig {
  /** `desktop` is the sidecar on the Steam Deck; `hosted` is the site. */
  mode: "desktop" | "hosted";
  /** Whether the hosted server answered a recent probe. Always true on it. */
  online: boolean;
  /** Where to go to play with friends. `null` on the hosted server. */
  remote_origin: string | null;
  app_version: string;
  /** The content package the desktop shell is running; `app_version` on the site. */
  content_version: string;
}

/**
 * How an imported card reached the engine.
 *
 * `native`  - a hand-written card in `data/cards/`, reused whole.
 * `full`    - generated, and nothing was lost (a vanilla creature, a land).
 * `partial` - generated, non-keyword rules text inert. `notes` says what.
 */
export type CardOrigin = "native" | "full" | "partial";

export interface ImportedCard {
  name: string;
  qty: number;
  card_id: string;
  origin: CardOrigin;
  notes: string[];
}

export interface DeckImportResponse {
  deck: DeckSummary;
  source: string;
  source_id: string;
  total: number;
  playable: number;
  simplified: number;
  /** Called out separately: a deck can look like 37 lands and behave like 34. */
  lands: number;
  lands_producing_mana: number;
  /** Lands with no abilities at all. A fetchland makes no mana and is not one. */
  lands_inert: number;
  cards: ImportedCard[];
  problems: string[];
  /** What the desktop build's art fetch did; `null` on the site. */
  art_prefetch?: ArtPrefetch | null;
}

/** An imported deck's art on the desktop build, and the verdict. */
export interface ArtPrefetch {
  fetched: number;
  cached: number;
  failed: string[];
  /** Every illustration the deck can have is on this machine. */
  complete: boolean;
  /** Card ids with a printing somewhere and no file here yet. */
  missing: string[];
}

/** One deck `POST /api/decks/complete` looked at. */
export interface DeckCompletion {
  deck_id: string;
  fetched: number;
  complete: boolean;
  missing: string[];
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
  /** Same-origin path, or null when the card has no printing. */
  art_url: string | null;
  artist: string | null;
}

/**
 * `GET /api/images` -- where every engine card's art lives.
 *
 * Deliberately carries no `cards.scryfall.io` URL. The server owns the bytes
 * and serves them itself, so the board renders with no third-party dependency
 * at all. A `null` value means that card has no printing anywhere and the
 * client should draw its "no art" plate rather than request a 404.
 */
export interface ImagesResponse {
  art_base: string;
  images: Record<string, { card_id: string; art: string | null; artist: string | null } | null>;
  /**
   * `seat index -> card id -> ref`, for the cards a seat's deck prints
   * differently from the catalog's pick -- the illustration its author chose on
   * Moxfield. Absent without `?game_id=`, and empty for a deck that named none.
   *
   * A second layer rather than an edit to `images` because two seats can hold
   * the same card id and want different art, which a flat map cannot say. The
   * key is `CardView.owner`, so nothing extra has to be looked up to use it.
   */
  seats?: Record<
    string,
    Record<string, { card_id: string; art: string | null; artist: string | null }>
  >;
}

/* ------------------------------------------------------------------ */
/* Decks: the dossier's half                                           */
/* ------------------------------------------------------------------ */

/** Five 1-4 scales. Editorial: an imported deck has none of this. */
export interface DeckRatings {
  speed: number;
  complexity: number;
  interaction: number;
  resilience: number;
  pilot: number;
}

export interface SignatureCard {
  card_id: string;
  name: string;
  why: string;
  art_url: string | null;
}

/** `GET /api/decks/{id}` -- everything the dossier shows. */
export interface DeckDetail extends DeckSummary {
  ratings: DeckRatings | null;
  strategy: string;
  signature: SignatureCard[];
  /** Seven buckets: mana values 1..6 and 7+, non-lands only. */
  curve: number[];
  lands: number;
  swaps: number;
  swap_note: string;
}

/* ------------------------------------------------------------------ */
/* Pods: the pre-game lobby                                            */
/* ------------------------------------------------------------------ */

export type PodSeatKind = "empty" | "cpu" | "open" | "human";
export type PodStatus = "open" | "starting" | "in_game" | "closed";

export interface PodSeatView {
  index: number;
  kind: PodSeatKind;
  name: string | null;
  /**
   * Null until this seat locks in -- the lobby's hidden-information rule, and
   * the reason a face-down card is one picture for three different facts.
   */
  deck: DeckSummary | null;
  locked: boolean;
  ready: boolean;
  is_you: boolean;
  is_host: boolean;
  /** CPU seats only. */
  agent: string | null;
}

export interface PodView {
  code: string;
  /** Monotonic. Fed back as `?since=` to long-poll for somebody else's move. */
  version: number;
  status: PodStatus;
  seats: PodSeatView[];
  your_seat: number | null;
  you_are_host: boolean;
  /** Set the moment the host deals; how every client finds the table. */
  game_id: string | null;
  invite_link: string;
}

/** Returned exactly once, at create or join. The token is never in a PodView. */
export interface PodCredentials {
  player_token: string;
  pod: PodView;
}

export type SeatAdminAction = "add_cpu" | "open_chair" | "clear" | "set_deck" | "set_agent";
