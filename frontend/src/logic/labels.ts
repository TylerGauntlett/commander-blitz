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
  return `Turn ${state.turn} - ${active.name} - ${stepLabel(state.step)}`;
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

/**
 * One line of play-by-play, or null for events not worth showing.
 *
 * `viewerSeat` exists only for grammar: the viewer's own seat is "you", and
 * "you" takes a different verb form. Without it the log reads "You draws a
 * card" on every single draw, which is most of the log.
 */
export function describeEvent(
  event: GameEvent,
  names: string[],
  viewerSeat?: number,
): string | null {
  const who = event.player === null ? "" : (names[event.player] ?? `P${event.player}`);
  const isViewer = event.player !== null && event.player === viewerSeat;
  /** Pick the verb form that agrees with `who`. */
  const v = (second: string, third: string) => (isViewer ? second : third);
  const raw = typeof event.data.card === "string" ? event.data.card : null;
  const card = raw ? prettyCardName(raw) : null;
  switch (event.type) {
    case "turn_began":
      return `-- ${who}'s turn ${event.data.turn} --`;
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
    case "counter_placed":
      return `${event.data.amount} ${event.data.kind ?? ""} counter on ${card ?? "a permanent"}`.replace(
        /\s+/g,
        " ",
      );
    case "mill":
      return `${who} ${v("mill", "mills")} ${event.data.amount ?? 1}`;
    case "draw":
      return `${who} ${v("draw", "draws")} a card`;
    case "discard":
      return `${who} ${v("discard", "discards")} a card`;
    case "damage_dealt":
      return `${event.data.amount} damage to ${event.data.to === "player" ? who : "a permanent"}`;
    case "life_gained":
      return `${who} ${v("gain", "gains")} ${event.data.amount} life`;
    case "life_lost":
      return `${who} ${v("lose", "loses")} ${event.data.amount} life`;
    case "attackers_declared":
      return `${who} ${v("attack", "attacks")}`;
    case "blockers_declared":
      return "Blockers declared";
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
