/**
 * The assembly helpers every scenario module shares, and the `Scenario` shape.
 *
 * See `index.ts` for why the positions are built rather than written out.
 */

import type {
  CardView,
  GameEvent,
  GameView,
  LegalAction,
  ManaSourceView,
  PlayerView,
} from "../../api/types";
import * as pool from "../cards";
import { action, player } from "../fixtures";

export interface Scenario {
  state: GameView;
  actions: LegalAction[];
  events: GameEvent[];
}

/**
 * A mana source as the engine reports it.
 *
 * `options` and `symbols` are not the same fact and the orb draws both: "Add {G}
 * or {U}" is one mana with two options, "Add {G}{U}" is two mana with one.
 */
function source(oid: number, symbols: string[], amount = 1): ManaSourceView {
  return {
    oid,
    options: amount === 1 ? symbols.map((s) => [s]) : [symbols],
    symbols,
    amount,
  };
}

/** Untapped permanents that make mana, as the mana row would see them. */
function manaFrom(cards: CardView[]) {
  const sources = cards
    .filter((c) => !c.tapped && c.produces.length > 0)
    .map((c) => source(c.oid, c.produces, c.card_id === "sol_ring" ? 2 : 1));
  return {
    pool: {},
    sources,
    total: sources.reduce((sum, s) => sum + s.amount, 0),
  };
}

/** The viewer, wired so their board, hand and mana all describe each other. */
export function you(
  overrides: Partial<PlayerView> = {},
  battlefield: CardView[] = [],
): PlayerView {
  return player({
    pid: 0,
    name: "You",
    mana: manaFrom(battlefield.filter((c) => c.controller === 0)),
    hand_count: overrides.hand?.length ?? 0,
    library_count: 92,
    command: [pool.aesi({ oid: 900 })],
    ...overrides,
  });
}

/** An opponent: hand hidden, reasons null, as the server sends every other seat. */
export function opponent(
  pid: number,
  name: string,
  overrides: Partial<PlayerView> = {},
): PlayerView {
  return player({
    pid,
    name,
    deck_id: "edgar",
    hand: null,
    hand_reasons: null,
    hand_count: 7,
    library_count: 92,
    command: [pool.edgarMarkov({ oid: 900 + pid })],
    ...overrides,
  });
}

/** The action every priority window has, and the one the slab promotes. */
export const pass = action({ id: "a0-pass", kind: "pass", label: "Pass", base_label: "Pass" });
