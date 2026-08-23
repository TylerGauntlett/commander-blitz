/**
 * What an opponent is, in one line.
 *
 * "4 creatures - 2 untapped - 7 power - 1 flier" is the whole of what a player
 * needs from a seat they are not currently reading. It is the answer to the two
 * questions actually being asked across the table -- *can they kill me* and
 * *can they stop me* -- and it answers them without the reader counting
 * anything.
 *
 * On a handheld this is load-bearing: at 1280x800 an opponent's board cannot be
 * drawn at a card size anybody can read, so the summary IS the opponent and the
 * full board is one `R2` hold away. But it earns its place on a desktop too, and
 * that is why it is not scoped to the handheld layout. A four-player pod draws
 * opponents' cards at ~51px, where counting untapped creatures is a chore the
 * client can simply do for you.
 *
 * Everything here is derived from the view the server already sends. Nothing is
 * inferred, and in particular nothing here decides what is *legal* -- a summary
 * that disagreed with the action list would be worse than no summary.
 */

import type { CardView, GameView } from "../api/types";
import { groupBattlefield } from "./zoneGrouping";

export interface Threat {
  /** Creatures on the battlefield, tapped or not. */
  creatures: number;
  /** ...of which are untapped, which is what "can they block" means. */
  untapped: number;
  /** Total power on board. Damage they could point at somebody this turn. */
  power: number;
  /** Creatures with flying or reach -- what an evasive attack has to get past. */
  fliers: number;
  /**
   * Untapped mana sources.
   *
   * A *source* count, not a symbol count: "Add {G} or {U}" is one mana, and a
   * summary that read it as two would overstate what they can hold up. This is
   * the same distinction `ManaView` documents and `logic/mana.ts` respects.
   */
  openMana: number;
  /** Cards in hand. Unknown cards, but a known count, and the count matters. */
  hand: number;
  /** Non-land, non-creature permanents: the artifacts and enchantments row. */
  other: number;
}

/** Keywords that mean "this gets past a ground blocker". */
const EVASIVE = new Set(["flying", "reach"]);

function isCreature(card: CardView): boolean {
  return card.types.includes("Creature");
}

function flies(card: CardView): boolean {
  return card.keywords.some((keyword) => EVASIVE.has(keyword.toLowerCase()));
}

/**
 * Summarise one seat.
 *
 * `power` counts every creature rather than only the untapped ones, because the
 * question it answers is "how much damage is on that board", which a tapped
 * attacker will still be able to ask next turn.
 */
export function threatOf(state: GameView, pid: number): Threat {
  const player = state.players[pid];
  const lanes = groupBattlefield(state, pid);
  const creatures = lanes.Creatures.filter(isCreature);

  let power = 0;
  let untapped = 0;
  let fliers = 0;
  for (const card of creatures) {
    power += card.power ?? 0;
    if (!card.tapped) untapped += 1;
    if (flies(card)) fliers += 1;
  }

  return {
    creatures: creatures.length,
    untapped,
    power,
    fliers,
    // `mana.sources` is already only the untapped permanents that could be
    // tapped for mana, so this is a length rather than a filter.
    openMana: player?.mana?.sources?.length ?? 0,
    hand: player?.hand_count ?? 0,
    other: lanes["Artifacts & Enchantments"].length,
  };
}

/** One clause of the summary line. */
export interface ThreatPart {
  key: string;
  /** The number, drawn `tabular` so a changing count does not reflow the row. */
  value: number;
  /** Singular; the caller pluralises against `value`. */
  label: string;
}

/**
 * The summary as clauses, in the order they are read.
 *
 * EMPTY CLAUSES ARE DROPPED, and that is the whole reason this is a function
 * rather than a template. A seat with no fliers should not spend a fifth of a
 * narrow line saying "0 fliers" -- but a seat with one flier absolutely must
 * say so, because that is the fact that changes whether an attack gets through.
 * The creature count is the exception and is always present: "nothing on board"
 * is itself the most useful thing the line can say.
 */
export function threatParts(threat: Threat): ThreatPart[] {
  const parts: ThreatPart[] = [
    { key: "creatures", value: threat.creatures, label: "creature" },
  ];
  if (threat.untapped > 0) {
    parts.push({ key: "untapped", value: threat.untapped, label: "untapped" });
  }
  if (threat.power > 0) parts.push({ key: "power", value: threat.power, label: "power" });
  if (threat.fliers > 0) parts.push({ key: "fliers", value: threat.fliers, label: "flier" });
  if (threat.openMana > 0) parts.push({ key: "mana", value: threat.openMana, label: "open" });
  return parts;
}

/**
 * `untapped`, `power` and `open` are already adjectives or mass nouns.
 *
 * "2 untappeds" and "7 powers" are what a naive pluraliser produces, and a
 * summary with a grammar mistake in it is a summary the reader stops trusting.
 */
const UNCOUNTABLE = new Set(["untapped", "power", "open"]);

export function threatClause(part: ThreatPart): string {
  const plural =
    part.value === 1 || UNCOUNTABLE.has(part.label) ? part.label : `${part.label}s`;
  return `${part.value} ${plural}`;
}

/** The whole line, for a title-free tooltip replacement and for tests. */
export function threatLine(threat: Threat): string {
  return threatParts(threat).map(threatClause).join(" · ");
}
