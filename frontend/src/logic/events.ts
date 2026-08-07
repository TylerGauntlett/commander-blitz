/**
 * Turning the server's event log into playable animation beats.
 *
 * One HTTP response can carry three opponents' entire turns, because
 * `GameSession.drive_ai` runs every AI seat until a human must decide. The
 * state therefore *snaps*, and nothing about it is watchable. This module
 * converts that flat log into a timed queue -- floating numerals, spotlights,
 * banners -- which the narration layer plays over the top of the new state.
 *
 * Pure: no timers, no React. The queue is data; `state/narration.ts` runs it.
 */

import type { GameEvent } from "../api/types";
import { prettyCardName } from "./labels";

export type BeatAnchor = { kind: "player"; pid: number } | { kind: "object"; oid: number };

export type Tone = "neutral" | "damage" | "gain" | "loss" | "danger" | "good";

export interface Beat {
  id: string;
  /** Milliseconds to hold after showing this beat, before the next one. */
  hold: number;
  /** Play-by-play line, or null to leave the ticker alone. */
  text: string | null;
  /** A number that floats up off a player or a permanent. */
  float?: { anchor: BeatAnchor; value: string; tone: Tone };
  /** A card thrown up in the middle of the screen while it is being cast. */
  spotlight?: { cardId: string; name: string; controller: number };
  /** A brief highlight ring on a permanent. */
  flash?: { anchor: BeatAnchor; tone: Tone };
  /** A full-width sweep: turn changes, eliminations. */
  banner?: { text: string; tone: Tone };
  /** 0..1 screen shake intensity. */
  shake?: number;
}

export type NameLookup = (cardId: string) => string | undefined;

function nameOf(event: GameEvent, lookup?: NameLookup): string | null {
  const cardId = typeof event.data.card === "string" ? event.data.card : null;
  if (!cardId) return null;
  return lookup?.(cardId) ?? prettyCardName(cardId);
}

function num(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

/**
 * Events that are bookkeeping rather than drama.
 *
 * `combat_damage_to_player` is skipped because `damage_player` fires
 * `damage_dealt` first for the very same hit -- animating both would double
 * every combat numeral.
 */
const SILENT = new Set([
  "combat_damage_to_player",
  "step_ended",
  "step_began",
  "mana_added",
  "mana_spent",
  "mana_emptied",
  "zone_change",
  "leaves_battlefield",
  "untapped",
  "ability_resolved",
]);

/**
 * Build the beat queue for one batch of events.
 *
 * `names[pid]` are the player names; `lookup` resolves a card id such as
 * `"sol_ring"` to its printed name, falling back to a prettified id.
 */
export function beatsFor(events: GameEvent[], names: string[], lookup?: NameLookup): Beat[] {
  const beats: Beat[] = [];

  events.forEach((event, index) => {
    if (SILENT.has(event.type)) return;

    const id = `${index}-${event.type}`;
    const who = event.player === null ? "" : (names[event.player] ?? `P${event.player}`);
    const card = nameOf(event, lookup);
    const amount = num(event.data.amount);
    const push = (beat: Omit<Beat, "id">) => beats.push({ id, ...beat });

    switch (event.type) {
      case "turn_began":
        push({
          hold: 850,
          text: `-- ${who}'s turn ${event.data.turn} --`,
          banner: { text: `${who}'s Turn`, tone: "neutral" },
        });
        return;

      case "spell_cast":
        push({
          hold: 700,
          text: `${who} casts ${card ?? "a spell"}`,
          spotlight: {
            cardId: typeof event.data.card === "string" ? event.data.card : "",
            name: card ?? "a spell",
            controller: event.player ?? 0,
          },
        });
        return;

      case "spell_resolved":
        push({ hold: 180, text: null });
        return;

      case "spell_countered":
        push({
          hold: 650,
          text: `${card ?? "A spell"} is countered`,
          banner: { text: "Countered", tone: "danger" },
        });
        return;

      case "spell_fizzled":
        push({
          hold: 650,
          text: `${card ?? "A spell"} fizzles -- no legal targets`,
          banner: { text: "Fizzled", tone: "danger" },
        });
        return;

      case "land_played":
        push({
          hold: 260,
          text: `${who} plays ${card ?? "a land"}`,
          flash:
            event.source === null
              ? undefined
              : { anchor: { kind: "object", oid: event.source }, tone: "neutral" },
        });
        return;

      case "enters_battlefield":
        push({
          hold: 220,
          text: `${card ?? "A permanent"} enters the battlefield`,
          flash:
            event.source === null
              ? undefined
              : { anchor: { kind: "object", oid: event.source }, tone: "good" },
        });
        return;

      case "token_created":
        push({
          hold: 200,
          text: `${who} creates ${card ?? "a token"}`,
          flash:
            event.source === null
              ? undefined
              : { anchor: { kind: "object", oid: event.source }, tone: "good" },
        });
        return;

      case "dies":
        push({
          hold: 380,
          text: `${card ?? "A creature"} dies`,
          flash:
            event.source === null
              ? undefined
              : { anchor: { kind: "object", oid: event.source }, tone: "danger" },
        });
        return;

      case "damage_dealt": {
        if (amount === null || amount <= 0) return;
        const toPlayer = event.data.to === "player";
        const targetOid = num(event.data.oid);
        const anchor: BeatAnchor = toPlayer
          ? { kind: "player", pid: event.player ?? 0 }
          : { kind: "object", oid: targetOid ?? event.source ?? 0 };
        push({
          hold: 340,
          text: toPlayer
            ? `${who} takes ${amount} damage`
            : `${amount} damage to ${card ?? "a permanent"}`,
          float: { anchor, value: `-${amount}`, tone: "damage" },
          shake: toPlayer ? Math.min(1, amount / 12) : undefined,
        });
        return;
      }

      case "life_gained":
        if (amount === null) return;
        push({
          hold: 280,
          text: `${who} gains ${amount} life`,
          float: {
            anchor: { kind: "player", pid: event.player ?? 0 },
            value: `+${amount}`,
            tone: "gain",
          },
        });
        return;

      case "life_lost":
        if (amount === null) return;
        push({
          hold: 280,
          text: `${who} loses ${amount} life`,
          float: {
            anchor: { kind: "player", pid: event.player ?? 0 },
            value: `-${amount}`,
            tone: "loss",
          },
        });
        return;

      case "counter_placed": {
        const kind = typeof event.data.counter === "string" ? event.data.counter : "counter";
        push({
          hold: 220,
          text: `${card ?? "A permanent"} gets ${amount ?? 1} ${kind}`,
          float:
            event.source === null
              ? undefined
              : {
                  anchor: { kind: "object", oid: event.source },
                  value: `+${amount ?? 1} ${kind}`,
                  tone: "good",
                },
        });
        return;
      }

      case "attackers_declared":
        push({
          hold: 520,
          text: `${who} attacks`,
          banner: { text: "Attack!", tone: "damage" },
        });
        return;

      case "blockers_declared":
        push({ hold: 420, text: "Blockers declared" });
        return;

      case "draw":
        push({ hold: 110, text: `${who} draws a card` });
        return;

      case "discard":
        push({ hold: 200, text: `${who} discards ${card ?? "a card"}` });
        return;

      case "mill":
        push({ hold: 200, text: `${who} mills ${event.data.count ?? "some"} cards` });
        return;

      case "ability_triggered":
        push({ hold: 300, text: `${card ?? "An ability"} triggers` });
        return;

      case "ability_activated":
        push({ hold: 260, text: `${who} activates ${card ?? "an ability"}` });
        return;

      case "mulligan_taken":
        push({ hold: 200, text: `${who} mulligans` });
        return;

      case "hand_kept":
        push({ hold: 200, text: `${who} keeps ${event.data.cards ?? 7} cards` });
        return;

      case "player_lost":
        push({
          hold: 1100,
          text: `${who} is eliminated (${event.data.reason})`,
          banner: { text: `${who} is eliminated`, tone: "danger" },
          shake: 0.6,
        });
        return;

      case "game_over":
        push({ hold: 400, text: `Game over: ${event.data.result}` });
        return;

      default:
        return;
    }
  });

  return beats;
}

/** Total wall-clock time a queue will take at a given speed multiplier. */
export function queueDuration(beats: Beat[], speed: number): number {
  return beats.reduce((total, beat) => total + beat.hold / speed, 0);
}
