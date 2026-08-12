/** Human-readable strings for steps, decisions, cards and events. */

import type { GameEvent, GameView } from "../api/types";

/**
 * The engine's 13 steps, in order.
 *
 * Careful: the server sends `step` UPPERCASE ("DECLARE_ATTACKERS") and `phase`
 * lowercase ("precombat_main") in the same payload. This module is the only
 * place that should have to know that.
 */
export const STEP_ORDER = [
  "UNTAP",
  "UPKEEP",
  "DRAW",
  "PRECOMBAT_MAIN",
  "BEGIN_COMBAT",
  "DECLARE_ATTACKERS",
  "DECLARE_BLOCKERS",
  "FIRST_STRIKE_DAMAGE",
  "COMBAT_DAMAGE",
  "END_OF_COMBAT",
  "POSTCOMBAT_MAIN",
  "END_STEP",
  "CLEANUP",
] as const;

/**
 * The thirteen steps, grouped into the five phases players actually name.
 *
 * Thirteen equal ticks is thirteen things to read, and twelve of them are
 * never the answer to "where are we". Grouping lets the live phase expand into
 * its steps while the rest collapse to a word -- so the track says "Combat,
 * declaring blockers" instead of making you count pills.
 *
 * Every step keeps a label in the DOM regardless of which phase is open;
 * `e2e/smoke.spec.ts` asserts all thirteen are still there, because a step that
 * renders as a blank gap is the bug this display replaced.
 */
export const PHASES = [
  { name: "Beginning", steps: ["UNTAP", "UPKEEP", "DRAW"] },
  { name: "Main 1", steps: ["PRECOMBAT_MAIN"] },
  {
    name: "Combat",
    steps: [
      "BEGIN_COMBAT",
      "DECLARE_ATTACKERS",
      "DECLARE_BLOCKERS",
      "FIRST_STRIKE_DAMAGE",
      "COMBAT_DAMAGE",
      "END_OF_COMBAT",
    ],
  },
  { name: "Main 2", steps: ["POSTCOMBAT_MAIN"] },
  { name: "End", steps: ["END_STEP", "CLEANUP"] },
] as const;

const STEP_NAMES: Record<string, string> = {
  UNTAP: "Untap",
  UPKEEP: "Upkeep",
  DRAW: "Draw",
  PRECOMBAT_MAIN: "Main 1",
  BEGIN_COMBAT: "Begin combat",
  DECLARE_ATTACKERS: "Declare attackers",
  DECLARE_BLOCKERS: "Declare blockers",
  FIRST_STRIKE_DAMAGE: "First strike",
  COMBAT_DAMAGE: "Combat damage",
  END_OF_COMBAT: "End of combat",
  POSTCOMBAT_MAIN: "Main 2",
  END_STEP: "End step",
  CLEANUP: "Cleanup",
};

/** Compact labels for the phase track, where horizontal space is scarce. */
const STEP_SHORT: Record<string, string> = {
  UNTAP: "Untap",
  UPKEEP: "Upkeep",
  DRAW: "Draw",
  PRECOMBAT_MAIN: "Main 1",
  BEGIN_COMBAT: "Combat",
  DECLARE_ATTACKERS: "Attack",
  DECLARE_BLOCKERS: "Block",
  FIRST_STRIKE_DAMAGE: "1st Strike",
  COMBAT_DAMAGE: "Damage",
  END_OF_COMBAT: "End Cbt",
  POSTCOMBAT_MAIN: "Main 2",
  END_STEP: "End",
  CLEANUP: "Cleanup",
};

const PHASE_NAMES: Record<string, string> = {
  beginning: "Beginning",
  precombat_main: "Main Phase",
  combat: "Combat",
  postcombat_main: "Second Main",
  ending: "End Phase",
};

const DECISION_PROMPTS: Record<string, string> = {
  priority: "You have priority",
  declare_attackers: "Declare attackers",
  declare_blockers: "Declare blockers",
  mulligan: "Keep this hand?",
  discard_to_hand_size: "Discard down to seven",
  choose_objects: "Choose",
  choose_mode: "Choose a mode",
  choose_x: "Choose X",
  may: "Optional effect",
  choose_player: "Choose a player",
  commander_zone_change: "Commander zone change",
};

const LOSS_REASONS: Record<string, string> = {
  life: "life total hit zero",
  empty_library: "drew from an empty library",
  commander_damage: "21 commander damage",
  concede: "conceded",
};

export function stepLabel(step: string): string {
  return STEP_NAMES[step] ?? step;
}

export function stepShort(step: string): string {
  return STEP_SHORT[step] ?? step;
}

export function phaseLabel(phase: string): string {
  return PHASE_NAMES[phase] ?? phase;
}

export function lossReason(reason: string | null): string {
  if (!reason) return "";
  return LOSS_REASONS[reason] ?? reason.replace(/_/g, " ");
}

/**
 * A display name for a card id.
 *
 * Events carry the snake_case definition id, not the printed name, so
 * "sol_ring" would otherwise reach the play-by-play verbatim. Callers that have
 * seen the card in a zone should pass a real lookup; this is the fallback.
 */
export function prettyCardName(cardId: string): string {
  return cardId
    .split("_")
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

export function decisionPrompt(state: GameView): string {
  const pending = state.pending;
  if (state.game_over) {
    if (state.winners.includes(state.seat)) return "You win!";
    if (state.winners.length === 0) return "The game is a draw.";
    return "You lose.";
  }
  if (!pending) return "Waiting...";
  if (pending.player !== state.seat) {
    return `Waiting for ${state.players[pending.player].name}...`;
  }
  return pending.prompt || DECISION_PROMPTS[pending.kind] || pending.kind;
}

export function turnLabel(state: GameView): string {
  const active = state.players[state.active_player];
  // The round, matching PhaseTrack: "turn" to a player means a lap of the table.
  return `Turn ${state.round} - ${active.name} - ${stepLabel(state.step)}`;
}

/**
 * What the opponent is currently being asked, for the thinking indicator.
 *
 * A bare pulsing "Opponent thinking" told the player nothing, and a decision
 * that produces no events -- passing priority is the common one -- looked
 * identical to the game having hung. Naming the seat and the step at least
 * says *where* in the turn the wait is happening.
 */
export function thinkingLabel(state: GameView): string {
  const pending = state.pending;
  if (!pending || pending.player === state.seat) return "Thinking";
  const who = state.players[pending.player]?.name ?? `P${pending.player}`;
  const what =
    pending.kind === "declare_attackers"
      ? "declare attackers"
      : pending.kind === "declare_blockers"
        ? "declare blockers"
        : pending.kind === "mulligan"
          ? "mulligan"
          : stepLabel(state.step).toLowerCase();
  return `${who} — ${what}`;
}

/** Resolves a card id such as "sol_ring" to its printed name. */
export type NameLookup = (cardId: string) => string | undefined;

/**
 * One line of play-by-play, or null for events not worth showing.
 *
 * THE ONLY PLACE THAT TURNS AN EVENT INTO PROSE. `beatsFor` used to carry its
 * own parallel switch over the same event types for `Beat.text`, which is how
 * triggers came to be missing from both of them at once, and why mana payment
 * narrated "You pays {2}{G}" while the log next to it said "You pay". Both
 * consumers now come through here; `logic/events.ts` owns timing, sound and
 * effects, and nothing else owns words.
 *
 * `viewerSeat` exists only for grammar: the viewer's own seat is "you", and
 * "you" takes a different verb form. Without it the log reads "You draws a
 * card" on every single draw, which is most of the log.
 *
 * `lookup` turns a card id into its printed name; without it the id is
 * prettified, which is close but not the same ("Kodamas Reach").
 */
export function describeEvent(
  event: GameEvent,
  names: string[],
  viewerSeat?: number,
  lookup?: NameLookup,
): string | null {
  const who = event.player === null ? "" : (names[event.player] ?? `P${event.player}`);
  const isViewer = event.player !== null && event.player === viewerSeat;
  /** Pick the verb form that agrees with `who`. */
  const v = (second: string, third: string) => (isViewer ? second : third);
  const raw = typeof event.data.card === "string" ? event.data.card : null;
  const card = raw ? (lookup?.(raw) ?? prettyCardName(raw)) : null;
  const amount = typeof event.data.amount === "number" ? event.data.amount : null;
  /** Possessive that agrees with `who`: "your", not "You's". */
  const whose = isViewer ? "Your" : `${who}'s`;
  switch (event.type) {
    case "turn_began":
      // The round, matching the phase track. `data.turn` is still on the event
      // for anything that needs the rules counter.
      return `-- ${whose} turn ${event.data.round ?? event.data.turn} --`;
    case "spell_cast":
      return `${who} ${v("cast", "casts")} ${card ?? "a spell"}`;
    case "spell_countered":
      return `${card ?? "A spell"} is countered`;
    case "spell_fizzled":
      return `${card ?? "A spell"} fizzles (no legal targets)`;
    case "land_played":
      return `${who} ${v("play", "plays")} ${card ?? "a land"}`;
    case "enters_battlefield":
      return `${card ?? "A permanent"} enters the battlefield`;
    case "dies":
      return `${card ?? "A creature"} dies`;
    // Triggers are most of what happens in Commander and used to appear in
    // neither the log nor the effects layer -- this switch and `beatsFor` are
    // independent, and both were missing a case.
    case "ability_triggered":
      return `${card ?? "An ability"} triggers`;
    case "ability_activated":
      return `${who} ${v("activate", "activates")} ${card ?? "an ability"}`;
    case "token_created":
      return `${who} ${v("create", "creates")} ${card ?? "a token"}`;
    // The permanent does not change zones, so no zone_change line covers this.
    // Without a line of its own a creature simply appears on the other side of
    // the board with nothing in the log to say why.
    // Same reason as control_changed: no zone change happens, so the card on
    // the board becomes a different card with nothing in the log to say why.
    case "transformed":
      return `${card ?? "A permanent"} transforms`;
    case "control_changed":
      return `${who} ${v("gain", "gains")} control of ${card ?? "a permanent"}`;
    case "counter_placed":
      return `${card ?? "A permanent"} gets ${amount ?? 1} ${
        typeof event.data.counter === "string" ? event.data.counter : "counter"
      }`;
    case "mill":
      return `${who} ${v("mill", "mills")} ${event.data.count ?? amount ?? 1} cards`;
    case "draw":
      return `${who} ${v("draw", "draws")} a card`;
    case "discard":
      return `${who} ${v("discard", "discards")} ${card ?? "a card"}`;
    case "cycled":
      return `${who} ${v("cycle", "cycles")} ${card ?? "a card"}`;
    case "damage_dealt":
      if (amount === null || amount <= 0) return null;
      return event.data.to === "player"
        ? `${who} ${v("take", "takes")} ${amount} damage`
        : `${amount} damage to ${card ?? "a permanent"}`;
    case "life_gained":
      return amount === null ? null : `${who} ${v("gain", "gains")} ${amount} life`;
    case "life_lost":
      return amount === null ? null : `${who} ${v("lose", "loses")} ${amount} life`;
    case "attackers_declared":
      return `${who} ${v("attack", "attacks")}`;
    case "blockers_declared":
      return "Blockers declared";
    // Payment used to be entirely silent, then was narrated by a second switch
    // with no verb agreement at all -- "You pays {2}{G}".
    case "mana_spent":
      return typeof event.data.mana === "string"
        ? `${who} ${v("pay", "pays")} ${event.data.mana}`
        : null;
    case "mulligan_taken":
      return `${who} ${v("mulligan", "mulligans")}`;
    case "hand_kept":
      return `${who} ${v("keep", "keeps")} ${event.data.cards ?? 7} cards`;
    case "player_lost":
      return `${who} is eliminated (${lossReason(String(event.data.reason))})`;
    case "game_over":
      return `Game over: ${event.data.result}`;
    default:
      return null;
  }
}

export function playerNames(state: GameView): string[] {
  return state.players.map((player) => player.name);
}
