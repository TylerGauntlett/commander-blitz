/**
 * Turning the server's event log into playable animation beats.
 *
 * One HTTP response can carry three opponents' entire turns, because
 * `GameSession.drive_ai` runs every AI seat until a human must decide. The
 * state therefore *snaps*, and nothing about it is watchable. This module
 * converts that flat log into a timed queue -- floating numerals, spotlights,
 * banners, departing cards -- which the narration layer plays over the top of
 * the new state.
 *
 * "Over the top of the new state" is why `exits` carries as much as it does.
 * Every other beat anchors to something the board is still drawing; a card that
 * has just been destroyed is by definition one the board has stopped drawing,
 * so the beat has to name it well enough to be reconstructed from nothing.
 *
 * Pure: no timers, no React. The queue is data; `state/narration.ts` runs it.
 */

import type { GameEvent } from "../api/types";
import type { SoundName } from "../audio/sfx";
import { type NameLookup, describeEvent, exitPhrase, prettyCardName } from "./labels";

export type { NameLookup };

export type BeatAnchor = { kind: "player"; pid: number } | { kind: "object"; oid: number };

export type Tone = "neutral" | "damage" | "gain" | "loss" | "danger" | "good";

/**
 * One permanent leaving the battlefield, with everything needed to draw it.
 *
 * Carries the *identity* of the card rather than the card itself: the FX layer
 * resolves a face when the beat plays, by which point the card is in the
 * destination zone -- or, for a token, nowhere at all.
 */
export interface ExitFx {
  oid: number;
  /** The definition id, for the token fallback. See `FxLayer`. */
  cardId: string;
  name: string;
  /** Whose pile it lands in. `zone_change` reports the owner as `player`. */
  owner: number;
  /**
   * The destination the engine actually used, never one inferred from `cause`:
   * rule 903.9a sends a *destroyed commander* to the command zone.
   */
  to: string;
  cause: string;
  /** Ready-made prose, so the layer that draws it owns no words. */
  caption: string;
}

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
  /**
   * Permanents leaving the battlefield, drawn as cards flying into their pile.
   *
   * Plural, and that is the point: a wrath emits one `zone_change` per
   * permanent, and a beat each would hold the board for six seconds. A run of
   * them collapses into one beat and the FX layer staggers the ghosts inside
   * it, which is what that layer says it exists for.
   */
  exits?: ExitFx[];
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
  // `zone_change` now owns every departure -- it knows the destination *and*
  // the cause, and `move_object` emits it alongside both of these for the same
  // card. Leaving `dies` audible would toll twice for one creature and flash an
  // oid that is no longer in the DOM, which is what it did for its whole life.
  "dies",
  "leaves_battlefield",
  "untapped",
  "ability_resolved",
]);

/**
 * A battlefield departure, or null for any other zone change.
 *
 * The guard is doing two jobs. Anything that did not start on the battlefield
 * has no ghost to draw -- there is no card on screen to fly anywhere. And a
 * zone change out of a *library* carries a card id to every seat, so animating
 * one would show the table an opponent's tutor target.
 */
function exitFor(event: GameEvent, lookup?: NameLookup): ExitFx | null {
  if (event.type !== "zone_change" || event.data.from !== "battlefield") return null;
  const oid = typeof event.data.oid === "number" ? event.data.oid : null;
  const cardId = typeof event.data.card === "string" ? event.data.card : "";
  if (oid === null) return null;
  const cause = typeof event.data.cause === "string" ? event.data.cause : "";
  const to = typeof event.data.to === "string" ? event.data.to : "graveyard";
  const byId = typeof event.data.by_card === "string" ? event.data.by_card : null;
  const by = byId ? (lookup?.(byId) ?? prettyCardName(byId)) : null;
  return {
    oid,
    cardId,
    name: cardId ? (lookup?.(cardId) ?? prettyCardName(cardId)) : "A permanent",
    owner: event.player ?? 0,
    to,
    cause,
    caption: exitPhrase(cause, by, to),
  };
}

/** Destinations worth a funeral toll. A bounced creature is not one. */
const SOLEMN_ZONES = new Set(["graveyard", "exile"]);

/**
 * Group each *consecutive run* of departures onto its leading event.
 *
 * Consecutive, not global: "a creature dies, a trigger resolves, another
 * creature dies" is two moments and collapsing them would put the second death
 * on screen before the trigger that caused it. A run survives intervening
 * events that produce no beat of their own -- which is what lets a wrath, whose
 * every death also fires a silent `dies` and `leaves_battlefield`, still read as
 * one sweep.
 */
function groupExits(
  events: GameEvent[],
  lookup?: NameLookup,
): { leaders: Map<number, ExitFx[]>; absorbed: Set<number> } {
  const leaders = new Map<number, ExitFx[]>();
  const absorbed = new Set<number>();
  let openRun: number | null = null;

  events.forEach((event, index) => {
    const exit = exitFor(event, lookup);
    if (exit) {
      if (openRun === null) {
        openRun = index;
        leaders.set(index, [exit]);
      } else {
        leaders.get(openRun)?.push(exit);
        absorbed.add(index);
      }
      return;
    }
    // Only something that would itself be narrated closes a run.
    if (!SILENT.has(event.type)) openRun = null;
  });

  return { leaders, absorbed };
}

/**
 * How long the board holds while a run of departures plays.
 *
 * Deliberately sublinear. Ten deaths at a readable single-death pace would stall
 * the turn for six seconds; the ghosts are staggered inside the FX layer
 * instead, and keep flying after the queue has moved on -- floats already work
 * exactly this way.
 */
function exitHold(count: number): number {
  return Math.min(820, 420 + (count - 1) * 100);
}

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
  const { leaders, absorbed } = groupExits(events, lookup);

  events.forEach((event, index) => {
    if (SILENT.has(event.type)) return;
    // Folded into the run its leader carries.
    if (absorbed.has(index)) return;

    const id = `${index}-${event.type}`;
    const who = event.player === null ? "" : (names[event.player] ?? `P${event.player}`);
    const card = nameOf(event, lookup);
    const amount = num(event.data.amount);
    const text = describeEvent(event, names, viewerSeat, lookup);
    const push = (beat: Omit<Beat, "id" | "text">, override?: string | null) =>
      beats.push({ id, text: override === undefined ? text : override, ...beat });

    const exits = leaders.get(index);
    if (exits) {
      const solemn = exits.some((exit) => SOLEMN_ZONES.has(exit.to));
      push(
        {
          hold: exitHold(exits.length),
          exits,
          sound: solemn ? "toll" : undefined,
          // A wrath is a big enough moment to feel; a single death is not.
          shake: exits.length >= 4 ? Math.min(0.7, exits.length / 10) : undefined,
        },
        // The ticker lists every departure independently, so the beat only
        // needs the headline. Past a pair, naming one of them would be odd.
        exits.length > 2 ? `${exits.length} permanents leave the battlefield` : text,
      );
      return;
    }

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

      /*
       * A copy going on the stack. Short, because storm puts several up at
       * once and a full cast-length beat each would stall the turn -- but not
       * silent, since a copy is the difference between one bolt and nine.
       */
      case "spell_copied":
        push({ hold: 200, sound: "chime" });
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
