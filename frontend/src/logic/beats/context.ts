/** The small helpers every per-event beat shares, and the context it is built from. */

import type { GameEvent } from "../../api/types";
import { type NameLookup, prettyCardName } from "../labels";
import type { Beat, BeatAnchor, TimedFx, Tone } from "./types";

export function nameOf(event: GameEvent, lookup?: NameLookup): string | null {
  const cardId = typeof event.data.card === "string" ? event.data.card : null;
  if (!cardId) return null;
  return lookup?.(cardId) ?? prettyCardName(cardId);
}

export function num(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

/**
 * A permanent hitting the table.
 *
 * Dust under the card and a short squash, so an arrival has some mass to it.
 * Nothing here adds to the beat's `hold` -- both effects outlive it, exactly as
 * a floating numeral does, so the board gets heavier without getting slower.
 */
export function arrival(source: number | null): TimedFx[] {
  if (source === null) return [];
  return [
    { at: 0, kind: "emit", preset: "dust", at_point: { kind: "object", oid: source } },
    { at: 0, kind: "actuate", oid: source, move: "pulse", power: 0.8 },
    /*
     * A permanent hitting the table is the single most frequent thing that
     * happens in a game of Magic, and until now it made no sound and threw no
     * light -- a puff of dust and a scale pulse, both of which are easy to miss
     * on a busy board and impossible to notice if you happened to be reading
     * your hand.
     *
     * `thump` already exists for exactly this ("a card landing on the table:
     * low, dull, over immediately") and was never wired to an arrival. The
     * flash is the same beat in the visual channel, for a player with sound off
     * -- which on a handheld is most of them.
     */
    { at: 0, kind: "sound", sound: "thump" },
    { at: 20, kind: "flash", at_point: { kind: "object", oid: source }, tone: "neutral" },
  ];
}

/**
 * What one event's beat is built from: the event, the words already chosen for
 * it, and the `push` that stamps them onto the queue. See `beatsFor`.
 */
export interface EventContext {
  event: GameEvent;
  /** The acting player's name, or "" for a table event. */
  who: string;
  /** The card's printed name, when the event carries one. */
  card: string | null;
  amount: number | null;
  viewerSeat: number | undefined;
  push: (beat: Omit<Beat, "id" | "text">, override?: string | null) => void;
  /** A flash on whatever this event came from, or nothing to flash. */
  onSource: (tone: Tone) => { anchor: BeatAnchor; tone: Tone } | undefined;
}
