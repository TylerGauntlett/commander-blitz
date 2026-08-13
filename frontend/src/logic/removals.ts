/**
 * How each card in a graveyard or exile pile got there.
 *
 * The exit animation answers "why did that die" for about a second. This
 * answers it afterwards, when the player opens the pile and wants to audit a
 * board they were not watching closely -- which of my creatures did they
 * exile, and with what.
 *
 * Derived entirely from the event log the client already keeps: the server view
 * of a graveyard is a flat list of cards with no history on it, and asking it to
 * carry one would mean persisting a cause per object for the whole game.
 * `useGame` accumulates every event it has been sent, so the fold is free.
 *
 * Undo replaces that log wholesale rather than appending to it, which is
 * exactly right here -- the map is rebuilt from whatever the log now says, so a
 * rewound death stops being reported without anything having to forget it.
 */

import type { GameEvent } from "../api/types";
import { type NameLookup, exitPhrase, prettyCardName } from "./labels";

/**
 * oid -> the phrase describing how it left the battlefield.
 *
 * Only departures *from* the battlefield are recorded. Everything else either
 * has no interesting story (a drawn card was drawn) or is hidden information: a
 * library-origin zone change carries a card id to every seat, so folding those
 * in would let a player read an opponent's tutor out of their own graveyard
 * modal.
 */
export function removalsByOid(events: GameEvent[], lookup?: NameLookup): Map<number, string> {
  const notes = new Map<number, string>();
  for (const event of events) {
    if (event.type !== "zone_change" || event.data.from !== "battlefield") continue;
    const oid = typeof event.data.oid === "number" ? event.data.oid : null;
    if (oid === null) continue;
    const cause = typeof event.data.cause === "string" ? event.data.cause : "";
    const byId = typeof event.data.by_card === "string" ? event.data.by_card : null;
    const by = byId ? (lookup?.(byId) ?? prettyCardName(byId)) : null;
    const to = typeof event.data.to === "string" ? event.data.to : undefined;
    // Last write wins: a creature can leave the battlefield, come back and
    // leave again, and it is the most recent departure that put it where the
    // player is now looking at it.
    notes.set(oid, exitPhrase(cause, by, to));
  }
  return notes;
}
