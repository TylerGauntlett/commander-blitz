/** Human-readable strings for steps, decisions and events. */

import type { GameEvent, GameView } from "../api/types";

const STEP_NAMES: Record<string, string> = {
  UNTAP: "Untap",
  UPKEEP: "Upkeep",
  DRAW: "Draw",
  PRECOMBAT_MAIN: "Main 1",
  BEGIN_COMBAT: "Begin combat",
  DECLARE_ATTACKERS: "Declare attackers",
  DECLARE_BLOCKERS: "Declare blockers",
  FIRST_STRIKE_DAMAGE: "First strike damage",
  COMBAT_DAMAGE: "Combat damage",
  END_OF_COMBAT: "End of combat",
  POSTCOMBAT_MAIN: "Main 2",
  END_STEP: "End step",
  CLEANUP: "Cleanup",
};

const DECISION_PROMPTS: Record<string, string> = {
  priority: "You have priority",
  declare_attackers: "Declare attackers",
  declare_blockers: "Declare blockers",
  mulligan: "Keep this hand?",
  choose_objects: "Choose",
  choose_mode: "Choose a mode",
  may: "Optional effect",
  choose_player: "Choose a player",
};

export function stepLabel(step: string): string {
  return STEP_NAMES[step] ?? step;
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

/** One line of play-by-play, or null for events not worth showing. */
export function describeEvent(event: GameEvent, names: string[]): string | null {
  const who = event.player === null ? "" : (names[event.player] ?? `P${event.player}`);
  const card = typeof event.data.card === "string" ? event.data.card : null;
  switch (event.type) {
    case "turn_began":
      return `-- ${who}'s turn ${event.data.turn} --`;
    case "spell_cast":
      return `${who} casts ${card ?? "a spell"}`;
    case "spell_countered":
      return `${card ?? "A spell"} is countered`;
    case "spell_fizzled":
      return `${card ?? "A spell"} fizzles (no legal targets)`;
    case "land_played":
      return `${who} plays ${card ?? "a land"}`;
    case "enters_battlefield":
      return `${card ?? "A permanent"} enters the battlefield`;
    case "dies":
      return `${card ?? "A creature"} dies`;
    case "draw":
      return `${who} draws a card`;
    case "discard":
      return `${who} discards a card`;
    case "damage_dealt":
      return `${event.data.amount} damage to ${event.data.to === "player" ? who : "a permanent"}`;
    case "life_gained":
      return `${who} gains ${event.data.amount} life`;
    case "life_lost":
      return `${who} loses ${event.data.amount} life`;
    case "attackers_declared":
      return `${who} attacks`;
    case "blockers_declared":
      return "Blockers declared";
    case "player_lost":
      return `${who} is eliminated (${event.data.reason})`;
    case "game_over":
      return `Game over: ${event.data.result}`;
    default:
      return null;
  }
}

export function playerNames(state: GameView): string[] {
  return state.players.map((player) => player.name);
}
