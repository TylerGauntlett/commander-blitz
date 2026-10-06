/** Events, for the log and the FX layer. */

import type { CardView, GameEvent } from "../../api/types";
import { card, gameEvent } from "../fixtures";

/**
 * A turn's worth of log, covering the event kinds that render differently.
 *
 * The card id goes in `data.card` -- that is what the engine emits
 * (`state.emit(..., card=card.id)`) and what `describeEvent` and `beatsFor` both
 * read. `data.card_id` is the plausible-looking spelling, and it degrades into
 * "casts a spell" on every line: grammatical, unremarkable, and wrong.
 */
export function mixedLog(): GameEvent[] {
  return [
    gameEvent({ type: "turn_began", player: 0, data: { round: 4, turn: 7 } }),
    gameEvent({ type: "land_played", player: 0, data: { card: "forest" } }),
    gameEvent({ type: "spell_cast", player: 0, data: { card: "thragtusk" } }),
    gameEvent({ type: "spell_countered", player: 1, data: { card: "thragtusk" } }),
    gameEvent({ type: "enters_battlefield", player: 1, data: { card: "grizzly_bears" } }),
    gameEvent({ type: "ability_triggered", player: 0, data: { card: "rhystic_study" } }),
    // A death is two events, always: `move_object` emits the zone change and
    // fires `dies` together. The zone change is the one that carries the words
    // now, so a fixture with a bare `dies` would silently lose its line.
    gameEvent({
      type: "zone_change",
      player: 1,
      data: {
        card: "grizzly_bears",
        oid: 350,
        from: "battlefield",
        to: "graveyard",
        cause: "destroyed",
        by: 12,
        by_card: "swords_to_plowshares",
      },
    }),
    gameEvent({ type: "dies", player: 1, data: { card: "grizzly_bears" } }),
    gameEvent({ type: "token_created", player: 0, data: { card: "kraken_token" } }),
  ];
}

/** A card that exists nowhere the view can see, for the "unknown" branches. */
export function ghostCard(): CardView {
  return card({ oid: -1, card_id: "unknown_card", name: "Unknown Card" });
}
