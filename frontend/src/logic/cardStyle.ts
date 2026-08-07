/**
 * Deriving a card's look from its rules data.
 *
 * Pure so it can be unit tested, and so the card component stays a renderer.
 */

import type { CardView } from "../api/types";

export type FrameTone = "W" | "U" | "B" | "R" | "G" | "C" | "gold" | "land";

/**
 * The frame colour, following the usual convention: one colour uses that
 * colour, two or more use gold, no colour is either land or artifact grey.
 */
export function frameTone(card: CardView): FrameTone {
  if (card.types.includes("Land")) return "land";
  const colors = card.colors;
  if (colors.length === 0) return "C";
  if (colors.length > 1) return "gold";
  const only = colors[0];
  if (only === "W" || only === "U" || only === "B" || only === "R" || only === "G") {
    return only;
  }
  return "C";
}

export type TypeTone =
  | "creature"
  | "land"
  | "artifact"
  | "enchantment"
  | "instant"
  | "sorcery"
  | "planeswalker"
  | "other";

/**
 * Precedence when a card has several types, most decision-relevant first.
 *
 * An Artifact Creature attacks and blocks, so it reads as a creature; what it
 * is made of matters far less than what it does. Land wins outright, matching
 * `frameTone`, because a creature-land's first job is still to tap for mana.
 */
const TYPE_PRECEDENCE: ReadonlyArray<[string, TypeTone]> = [
  ["Land", "land"],
  ["Creature", "creature"],
  ["Planeswalker", "planeswalker"],
  ["Instant", "instant"],
  ["Sorcery", "sorcery"],
  ["Enchantment", "enchantment"],
  ["Artifact", "artifact"],
];

/**
 * The card's type, for the body fill.
 *
 * Colour identity already owns the border and interaction state owns the outer
 * glow, so type gets the largest channel left: the stock itself. The point is
 * scanning a pod board where the type line renders at under 6px -- see
 * docs/playtest-feedback-01.md item 4.
 */
export function typeTone(card: CardView): TypeTone {
  for (const [type, tone] of TYPE_PRECEDENCE) {
    if (card.types.includes(type)) return tone;
  }
  return "other";
}

/**
 * A shape for the title bar, carrying the same fact as the body fill.
 *
 * Deliberately redundant with colour. It survives red-green deficiency, and it
 * stays readable at 82px inside a stack ply where the fill is mostly occluded.
 * Geometric shapes rather than emoji: they render in every font, and they still
 * read in a greyscale screenshot, which is the check the doc asks for.
 */
const TYPE_GLYPHS: Record<TypeTone, string> = {
  creature: "◆", // filled diamond
  land: "▲", // triangle, an earth mark
  artifact: "■", // square
  enchantment: "✦", // four-pointed star
  instant: "»", // guillemet, reads as "any time"
  sorcery: "●", // filled circle
  planeswalker: "★", // star
  other: "·", // middle dot
};

export function typeGlyph(card: CardView): string {
  return TYPE_GLYPHS[typeTone(card)];
}

/** The word the glyph stands for, for `title` and screen readers. */
export function typeLabel(card: CardView): string {
  const tone = typeTone(card);
  return tone === "other" ? "Card" : tone.charAt(0).toUpperCase() + tone.slice(1);
}

export interface ManaPip {
  symbol: string;
  /** Stable within a cost: "{G}{G}" repeats a symbol, so position disambiguates. */
  key: string;
  /** The class suffix to colour it with; hybrids fall back to generic. */
  tone: string;
}

/**
 * Mana symbols split for pip rendering: "{4}{G}{U}" -> 4, G, U.
 *
 * The engine rejects hybrid and phyrexian costs at load time, so the only
 * symbols that reach here are numbers, WUBRG and C -- but a slash is still
 * mapped to `generic` rather than emitting an unmatchable class name.
 */
export function manaPips(manaCost: string): ManaPip[] {
  if (!manaCost || manaCost === "{0}") return [];
  return [...manaCost.matchAll(/\{([^}]*)\}/g)].map((match, index) => {
    const symbol = match[1];
    const simple = /^[WUBRGC]$/.test(symbol);
    return {
      symbol,
      key: `${index}-${symbol}`,
      tone: simple ? symbol : "generic",
    };
  });
}

/**
 * "2/2", or "" for a non-creature. Battlefield P/T has damage subtracted.
 *
 * The creature check is not redundant with the null check: on the battlefield
 * the server sends *derived* characteristics, and those are `0` rather than
 * `null` for a permanent with no P/T. Without it every land on the board wore
 * a "0/0" in its corner.
 */
export function statLine(card: CardView): string {
  if (!card.types.includes("Creature")) return "";
  if (card.power === null || card.toughness === null) return "";
  if (card.zone !== "battlefield") return `${card.power}/${card.toughness}`;
  return `${card.power}/${card.toughness - (card.damage ?? 0)}`;
}

/** True when the card is a creature that has taken damage but is still alive. */
export function isWounded(card: CardView): boolean {
  return card.zone === "battlefield" && (card.damage ?? 0) > 0;
}

/** Counters rendered as short badges, e.g. ["+1/+1 x3"]. */
export function counterBadges(card: CardView): string[] {
  const counters = card.counters ?? {};
  return Object.entries(counters)
    .filter(([, amount]) => amount > 0)
    .map(([kind, amount]) => (amount === 1 ? kind : `${kind} x${amount}`));
}

/** Keywords as they should read on a card face: "first_strike" -> "First strike". */
export function keywordLabel(keyword: string): string {
  const spaced = keyword.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
