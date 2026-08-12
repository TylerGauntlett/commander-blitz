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
import type { SoundName } from "../audio/sfx";
import { type NameLookup, describeEvent, prettyCardName } from "./labels";

export type { NameLookup };

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
  /**
   * A card thrown up in the middle of the screen while it is being cast, or an
   * ability announced as it goes on the stack. `kind` lets the two read
   * differently: a trigger is something happening *to* you and is not a card
   * leaving anyone's hand.
   */
  spotlight?: {
    cardId: string;
    name: string;
    controller: number;
    kind?: "spell" | "trigger";
  };
  /** A brief highlight ring on a permanent. */
  flash?: { anchor: BeatAnchor; tone: Tone };
  /** A full-width sweep: turn changes, eliminations. */
  banner?: { text: string; tone: Tone };
  /** 0..1 screen shake intensity. */
  shake?: number;
  /**
   * A sound to play with this beat.
   *
   * Named here rather than chosen by the effects layer so the mapping stays in
   * the pure module with the rest of the beat's meaning -- and so it is
   * testable without a Web Audio context. Only `FxLayer` ever plays it.
   */
  sound?: SoundName;
}

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
  // `mana_added` fires per source during auto-payment and `tapped` already
  // flashes the same permanent -- narrating both would double every land.
  "mana_added",
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
 * `viewerSeat` is for verb agreement in the prose -- see `describeEvent`.
 *
 * This module owns *timing, sound and effects*. It used to own words as well,
 * in a switch that ran parallel to `describeEvent` over the same event types --
 * which is how triggers ended up missing from both at once, and why payment
 * narrated "You pays {2}{G}". `push` now fills `text` from the one shared
 * switch, so a new event kind gets its line in exactly one place.
 */
export function beatsFor(
  events: GameEvent[],
  names: string[],
  lookup?: NameLookup,
  viewerSeat?: number,
): Beat[] {
  const beats: Beat[] = [];

  events.forEach((event, index) => {
    if (SILENT.has(event.type)) return;

    const id = `${index}-${event.type}`;
    const who = event.player === null ? "" : (names[event.player] ?? `P${event.player}`);
    const card = nameOf(event, lookup);
    const amount = num(event.data.amount);
    const text = describeEvent(event, names, viewerSeat, lookup);
    const push = (beat: Omit<Beat, "id" | "text">) => beats.push({ id, text, ...beat });

    switch (event.type) {
      case "turn_began":
        push({
          hold: 850,
          banner: {
            text: event.player === viewerSeat ? "Your Turn" : `${who}'s Turn`,
            tone: "neutral",
          },
        });
        return;

      case "spell_cast":
        push({
          hold: 700,
          sound: "chime",
          spotlight: {
            cardId: typeof event.data.card === "string" ? event.data.card : "",
            name: card ?? "a spell",
            controller: event.player ?? 0,
          },
        });
        return;

      case "spell_resolved":
        push({ hold: 180 });
        return;

      case "spell_countered":
        push({
          hold: 650,
          banner: { text: "Countered", tone: "danger" },
        });
        return;

      case "spell_fizzled":
        push({
          hold: 650,
          banner: { text: "Fizzled", tone: "danger" },
        });
        return;

      case "land_played":
        push({
          hold: 260,
          sound: "thump",
          flash:
            event.source === null
              ? undefined
              : { anchor: { kind: "object", oid: event.source }, tone: "neutral" },
        });
        return;

      case "enters_battlefield":
        push({
          hold: 220,
          sound: "thump",
          flash:
            event.source === null
              ? undefined
              : { anchor: { kind: "object", oid: event.source }, tone: "good" },
        });
        return;

      case "token_created":
        push({
          hold: 200,
          flash:
            event.source === null
              ? undefined
              : { anchor: { kind: "object", oid: event.source }, tone: "good" },
        });
        return;

      // Both of these change what a card *is* without moving it, so the frame
      // redraws in place. Held longer than an ETB so the change reads as a play
      // rather than as a rendering glitch.
      case "transformed":
      case "control_changed":
        push({
          hold: 480,
          sound: "chime",
          flash:
            event.source === null
              ? undefined
              : { anchor: { kind: "object", oid: event.source }, tone: "good" },
        });
        return;

      case "dies":
        push({
          hold: 380,
          sound: "toll",
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
          sound: "hit",
          float: { anchor, value: `-${amount}`, tone: "damage" },
          shake: toPlayer ? Math.min(1, amount / 12) : undefined,
        });
        return;
      }

      case "life_gained":
        if (amount === null) return;
        push({
          hold: 280,
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
          sound: "hit",
          banner: { text: "Attack!", tone: "damage" },
        });
        return;

      case "blockers_declared":
        push({ hold: 420 });
        return;

      case "draw":
        push({ hold: 110, sound: "shuffle" });
        return;

      case "discard":
        push({ hold: 200 });
        return;

      /*
       * Cycling reads as one action even though it is a discard, a draw and
       * often a trigger. A slightly longer hold than a plain discard, because
       * what usually follows it is a trigger going on the stack and the two
       * running together is what makes "(Do this before you draw)" invisible.
       */
      case "cycled":
        push({ hold: 260 });
        return;

      case "mill":
        push({ hold: 200 });
        return;

      /*
       * Triggers get the same spotlight a cast gets.
       *
       * In Commander triggers are most of what happens, and a trigger going on
       * the stack is the moment the player most needs to notice -- it used to
       * be a 300ms pause with nothing on screen at all, since the text this
       * beat carried was never rendered and the ticker had no case for it.
       */
      case "ability_triggered":
        push({
          hold: 620,
          sound: "chime",
          spotlight: {
            cardId: typeof event.data.card === "string" ? event.data.card : "",
            name: card ?? "An ability",
            controller: event.player ?? 0,
            kind: "trigger",
          },
          flash:
            event.source === null
              ? undefined
              : { anchor: { kind: "object", oid: event.source }, tone: "good" },
        });
        return;

      case "ability_activated":
        push({
          hold: 320,
          flash:
            event.source === null
              ? undefined
              : { anchor: { kind: "object", oid: event.source }, tone: "neutral" },
        });
        return;

      /*
       * Targeting, which is where ward happens.
       *
       * The flash is on the permanent being *targeted*, not on the spell doing
       * it, and the tone is "danger" because from the board's point of view
       * this is a thing being aimed at. It matters more than a normal beat: ward
       * raises a payment prompt off this event, so without a flash the dialog
       * arrives with nothing on screen saying which creature it is about.
       */
      case "became_target": {
        const oid = typeof event.data.oid === "number" ? event.data.oid : null;
        if (oid === null) return; // the player-target form; the cast beat covers it
        push({
          hold: 300,
          flash: { anchor: { kind: "object", oid }, tone: "danger" },
        });
        return;
      }

      /*
       * The outcome of the block declaration, per attacker. Short holds: these
       * fire in a batch, one per attacker, immediately after the per-blocker
       * `blocks` beats, and a full-length hold each would stall the step on a
       * wide board. The tones are from the attacking player's point of view --
       * getting through is good, being blocked is not.
       */
      case "became_blocked":
      case "attacked_unblocked": {
        const oid = typeof event.data.oid === "number" ? event.data.oid : null;
        push({
          hold: 160,
          flash:
            oid === null
              ? undefined
              : {
                  anchor: { kind: "object", oid },
                  tone: event.type === "became_blocked" ? "danger" : "good",
                },
        });
        return;
      }

      /*
       * Mana payment, which used to be entirely invisible: lands tapped during
       * auto-payment with no indication of what was spent. `tapped` flashes the
       * specific permanent that paid; `mana_spent` names the total.
       */
      case "tapped":
        push({
          hold: 90,
          sound: "tap",
          flash:
            event.source === null
              ? undefined
              : { anchor: { kind: "object", oid: event.source }, tone: "neutral" },
        });
        return;

      case "mana_spent":
        push({ hold: 120 });
        return;

      case "mulligan_taken":
        push({ hold: 200 });
        return;

      case "hand_kept":
        push({ hold: 200 });
        return;

      case "player_lost":
        push({
          hold: 1100,
          sound: "toll",
          banner: { text: `${who} is eliminated`, tone: "danger" },
          shake: 0.6,
        });
        return;

      case "game_over":
        push({ hold: 400 });
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
