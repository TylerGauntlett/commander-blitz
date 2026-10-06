/** Which events stay silent, and how a run of battlefield departures becomes one beat. */

import type { GameEvent } from "../../api/types";
import { exitPhrase, type NameLookup, prettyCardName } from "../labels";
import type { ExitFx } from "./types";

/**
 * Events that are bookkeeping rather than drama.
 *
 * `combat_damage_to_player` is skipped because `damage_player` fires
 * `damage_dealt` first for the very same hit -- animating both would double
 * every combat numeral.
 */
export const SILENT = new Set([
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
  // Fired *beside* `dies` for the very same card, so that a trigger can tell a
  // sacrifice from a removal spell. Narrating it would toll a third time for
  // one creature, on top of the `zone_change` that already owns the departure.
  "sacrificed",
  "leaves_battlefield",
  // The graveyard's counterpart, and silent for the identical reason: fired
  // beside the `zone_change` that already owns the departure, for the very same
  // card, so that "whenever one or more cards leave your graveyard" has
  // something to hear. A beat here would toll a second time for one card and
  // flash an oid that has already left the graveyard pile in the DOM.
  "leaves_graveyard",
  "untapped",
  "ability_resolved",
  // Fired beside `attackers_declared` for the very same declaration -- one per
  // defending seat, so a batch attack trigger can be told which seat. The
  // declaration already owns the "Attack!" banner and the surge, so a beat here
  // would sound it again once per opponent swung at; and being *silent* is also
  // what keeps it from closing the declaration run in `planCombat`, which would
  // split one swing into two animations.
  "creatures_attacked_player",
  // The same arrangement one phase later: fired beside the per-creature
  // `combat_damage_to_player` above -- itself already silent here -- for the
  // very same hits, so a delayed "whenever one or more creatures you control
  // deal combat damage to one or more players this turn" can be told the whole
  // batch at once. `damage_dealt` owns the numeral for each hit; a beat for the
  // summary would sound the combat a second time.
  "creatures_dealt_combat_damage",
  // The per-creature summary of the same hits: once per dealing creature per
  // step, for "whenever this creature deals combat damage" to anything. Every
  // hit already has its own beat.
  "creature_dealt_combat_damage",
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
export const SOLEMN_ZONES = new Set(["graveyard", "exile"]);

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
export function groupExits(
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
export function exitHold(count: number): number {
  return Math.min(820, 420 + (count - 1) * 100);
}
