/**
 * What a press on a permanent with activated abilities should do.
 *
 * ONE ROUTER, TWO CALLERS. `useTableGestures.onBoardCard` (a click, or `A` on
 * the ring) and `useTableVerbs.secondary` (`X`) both used to decide this for
 * themselves, and they disagreed: the click toggled a selection on a Mind
 * Stone and started targeting with *every* ability's actions on a planeswalker,
 * while `X` posted whichever activate action the engine listed first -- for a
 * Mind Stone that is "{T}: Add {C}", silently, with the sacrifice ability one
 * index away. On a Steam Deck, where the panel is 230px wide and every ability
 * reads as the card's name followed by an ellipsis, the board press is the one
 * a player actually makes, so it has to answer the question properly.
 *
 * The answer is a value, not a side effect, so a unit test can table it:
 *
 *   - `act`:    one ability, one way to do it. Post it.
 *   - `target`: one ability that still needs something pointed at (or a choice
 *               between its variants). Enter targeting on exactly its ids.
 *   - `menu`:   several abilities. Ask which, in `AbilityMenu`, and then do
 *               whichever of the two above the chosen ability wants.
 *   - `none`:   nothing is offered.
 *
 * An ability is identified by `ability_index`; the engine sends it on every
 * activate action (`server/schemas.py:LegalActionDTO`). `base_label` is the
 * fallback for a server that does not, and is also what the row and the menu
 * item show -- see `abilityText`.
 */

import type { LegalAction } from "../api/types";
import { abilityText } from "./actionMatch";

export interface AbilityChoice {
  /** The ability's position on the card; `-1` when the server did not say. */
  index: number;
  /** The ability's own text, without the card name in front of it. */
  text: string;
  /** Every legal action for this ability: one per target tuple or option. */
  ids: string[];
  /** Whether choosing it still leaves a target or variant to pick. */
  targeted: boolean;
}

export type AbilityRoute =
  | { kind: "none" }
  | { kind: "act"; id: string }
  | { kind: "target"; ids: string[] }
  | { kind: "menu"; abilities: AbilityChoice[] };

/** The activate actions a permanent offers, grouped by ability, in card order. */
export function abilitiesOf(
  actions: readonly LegalAction[],
  oid: number,
  sourceName: string | null = null,
): AbilityChoice[] {
  const byKey = new Map<string, AbilityChoice>();
  for (const action of actions) {
    if (action.kind !== "activate" || action.source_oid !== oid) continue;
    const key =
      action.ability_index === null ? action.base_label : String(action.ability_index);
    const found = byKey.get(key);
    if (found) {
      found.ids.push(action.id);
      found.targeted ||= action.targets.length > 0;
      continue;
    }
    byKey.set(key, {
      index: action.ability_index ?? -1,
      text: abilityText(action.base_label, sourceName),
      ids: [action.id],
      targeted: action.targets.length > 0,
    });
  }
  return [...byKey.values()];
}

/** Which of the three things a press on `oid` should do. */
export function abilityRoute(
  actions: readonly LegalAction[],
  oid: number,
  sourceName: string | null = null,
): AbilityRoute {
  const abilities = abilitiesOf(actions, oid, sourceName);
  if (abilities.length === 0) return { kind: "none" };
  if (abilities.length > 1) return { kind: "menu", abilities };
  return routeFor(abilities[0]);
}

/**
 * What a single, already-chosen ability wants next.
 *
 * Several ids with no target among them is still `target`: "Add one mana of
 * any colour" is five untargeted actions, and the panel's chips are where that
 * choice is drawn. Entering targeting on them is what lights the chips up and
 * sends the ring there (`followUp`'s `targeting` gesture falls through to the
 * panel rows when nothing on the board is a target).
 */
export function routeFor(ability: AbilityChoice): AbilityRoute {
  if (ability.ids.length === 1 && !ability.targeted) return { kind: "act", id: ability.ids[0] };
  return { kind: "target", ids: ability.ids };
}
