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
import { actionBeat } from "./beats/actions";
import { changeBeat } from "./beats/changes";
import { type EventContext, nameOf, num } from "./beats/context";
import { exitHold, groupExits, SILENT, SOLEMN_ZONES } from "./beats/exits";
import type { Beat, Tone } from "./beats/types";
import { planCombat } from "./choreography";
import { describeEvent, type NameLookup } from "./labels";

export type { NameLookup };

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
  // Combat is collapsed the same way departures are, and for the same reason:
  // the interesting unit is the exchange, not the individual hit. See
  // `logic/choreography.ts` -- this is what turned a 3.3-second slideshow into
  // one motion.
  const combat = planCombat(events, (type) => SILENT.has(type), viewerSeat);

  events.forEach((event, index) => {
    if (SILENT.has(event.type)) return;
    // Folded into the run its leader carries.
    if (absorbed.has(index)) return;
    if (combat.absorbed.has(index)) return;

    const id = `${index}-${event.type}`;
    const who = event.player === null ? "" : (names[event.player] ?? `P${event.player}`);
    const card = nameOf(event, lookup);
    const amount = num(event.data.amount);
    const text = describeEvent(event, names, viewerSeat, lookup);
    const push = (beat: Omit<Beat, "id" | "text">, override?: string | null) =>
      beats.push({ id, text: override === undefined ? text : override, ...beat });

    /*
     * A combat run replaces every beat its events would have produced.
     *
     * The prose is still `describeEvent`'s: a declaration says who is swinging,
     * and the strike stays wordless because the ticker already lists every hit
     * and a beat-level line would repeat it.
     */
    const exchange = combat.leaders.get(index);
    if (exchange) {
      beats.push({ ...exchange, text: combat.wordless.has(index) ? null : text });
      return;
    }

    /** A flash on whatever this event came from, or nothing to flash. */
    const onSource = (tone: Tone) =>
      event.source === null
        ? undefined
        : ({ anchor: { kind: "object", oid: event.source }, tone } as const);

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

    // The rest is one event, one beat, and the two halves of that switch are
    // `logic/beats/changes.ts` and `logic/beats/actions.ts`. Each answers only
    // for its own event types, so at most one of them builds anything.
    const ctx: EventContext = { event, who, card, amount, viewerSeat, push, onSource };
    if (changeBeat(ctx)) return;
    actionBeat(ctx);
  });

  return beats;
}

/** Total wall-clock time a queue will take at a given speed multiplier. */
export function queueDuration(beats: Beat[], speed: number): number {
  return beats.reduce((total, beat) => total + beat.hold / speed, 0);
}
