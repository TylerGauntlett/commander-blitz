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
 *   - `menu`:   several abilities, or one ability with several yields (a
 *               Treasure's five colours). Ask which, in `AbilityMenu`, and
 *               then do whatever the chosen item wants -- which, for an
 *               ability chosen from a menu, can be a second menu of its yields.
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
  /**
   * Each id's `option_label`, in step with `ids`: what that copy yields when the
   * copies differ by something other than a target -- "{R}" for one of "Add
   * one mana of any color". Absent on an item that is already one of them.
   */
  options?: string[];
  /**
   * What the menu's stop and test id are named by, when `index` cannot say:
   * a shock land's two land drops are not abilities and have no index.
   */
  key?: string;
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
  /*
   * A MODAL DOUBLE-FACED CARD IS THE SAME QUESTION AGAIN: Malakir Rebirth is
   * cast, Malakir Mire is played, and both are offered for the one card in
   * hand. Without this the cast and the land drop went into targeting
   * together, where pressing a creature could only ever answer the cast and
   * nothing could answer the land -- neither face was choosable from the hand.
   * So when a card offers both, each face is a menu item: every cast copy (one
   * per target) behind "Cast ...", and the land drop as its own item.
   */
  const twoFaced =
    actions.some((a) => a.kind === "play_land" && a.source_oid === oid) &&
    actions.some((a) => a.kind === "cast" && a.source_oid === oid);
  for (const action of actions) {
    if (twoFaced && action.kind === "cast" && action.source_oid === oid) {
      const found = byKey.get("cast");
      if (found) {
        found.ids.push(action.id);
        found.targeted ||= action.targets.length > 0;
      } else {
        byKey.set("cast", {
          index: -1,
          // "Cast Malakir Rebirth // Malakir Mire" names both faces; the item
          // is the front one. A variant's suffix goes with it, since every
          // variant shares the item and targeting asks which.
          text: action.base_label.split(" // ")[0],
          ids: [action.id],
          targeted: action.targets.length > 0,
          key: "cast",
        });
      }
      continue;
    }
    if (
      twoFaced &&
      action.kind === "play_land" &&
      action.source_oid === oid &&
      !action.option_label
    ) {
      byKey.set(`land:${action.base_label}`, {
        index: -1,
        text: action.base_label,
        ids: [action.id],
        targeted: false,
        key: `land-${byKey.size}`,
      });
      continue;
    }
    /*
     * A LAND DROP WITH A CHOICE IN IT is the same question: "As this land
     * enters, you may pay 2 life. If you don't, it enters tapped." The engine
     * offers the two answers as two land drops, each saying what it does in
     * `option_label` ("Pay 2 life, untapped", "Tapped"), and the menu is where
     * a card with two things to do asks which. A plain land drop carries no
     * option label and stays a single press.
     */
    if (action.kind === "play_land" && action.source_oid === oid && action.option_label) {
      const key = `land:${action.option_label}`;
      byKey.set(key, {
        index: -1,
        text: action.option_label,
        ids: [action.id],
        targeted: false,
        key: `land-${byKey.size}`,
      });
      continue;
    }
    if (action.kind !== "activate" || action.source_oid !== oid) continue;
    const key =
      action.ability_index === null ? action.base_label : String(action.ability_index);
    const found = byKey.get(key);
    if (found) {
      found.ids.push(action.id);
      found.options?.push(action.option_label);
      found.targeted ||= action.targets.length > 0;
      continue;
    }
    byKey.set(key, {
      index: action.ability_index ?? -1,
      text: abilityText(action.base_label, sourceName),
      ids: [action.id],
      targeted: action.targets.length > 0,
      options: [action.option_label],
    });
  }
  // The spell first: it is the face printed on the front.
  const cast = byKey.get("cast");
  const rest = [...byKey.values()].filter((choice) => choice !== cast);
  return cast ? [cast, ...rest] : rest;
}

/**
 * An ability's yields, one menu item each, or `[]` when it has fewer than two.
 *
 * A TREASURE IS A QUESTION TOO. "Add one mana of any color" is one ability and
 * five actions, told apart only by `option_label`. Routed as targeting, the
 * choice lit five chips in the panel -- on a Steam Deck a 230px column the ring
 * has to be sent to, away from the card that was pressed. The menu asks on the
 * board, the way it asks a planeswalker which loyalty ability.
 *
 * Grouped by label rather than one item per id, so an ability that also takes
 * an X or a target keeps every copy of one colour behind one item, and
 * `routeFor` on that item goes on to the X or target the way it would have.
 */
function yieldsOf(ability: AbilityChoice): AbilityChoice[] {
  const { options } = ability;
  if (!options || options.some((label) => label === "")) return [];
  const byLabel = new Map<string, AbilityChoice>();
  ability.ids.forEach((id, i) => {
    const found = byLabel.get(options[i]);
    if (found) {
      found.ids.push(id);
      return;
    }
    byLabel.set(options[i], {
      index: ability.index,
      text: options[i],
      ids: [id],
      targeted: ability.targeted,
      key: `${ability.key ?? ability.index}-yield-${byLabel.size}`,
    });
  });
  return byLabel.size > 1 ? [...byLabel.values()] : [];
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
 * Several yields are a `menu` of them (`yieldsOf`). Several ids that differ by
 * something the server did not name -- a target, an X -- are `target`:
 * entering targeting on them is what lights the board or the panel's chips up
 * and sends the ring there (`followUp`'s `targeting` gesture falls through to
 * the panel rows when nothing on the board is a target).
 */
export function routeFor(ability: AbilityChoice): AbilityRoute {
  const yields = yieldsOf(ability);
  if (yields.length > 0) return { kind: "menu", abilities: yields };
  if (ability.ids.length === 1 && !ability.targeted) return { kind: "act", id: ability.ids[0] };
  return { kind: "target", ids: ability.ids };
}
