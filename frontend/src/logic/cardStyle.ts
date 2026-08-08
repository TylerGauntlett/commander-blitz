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

export type LandTone = "W" | "U" | "B" | "R" | "G" | "C" | "multi";

const COLOR_SYMBOLS = ["W", "U", "B", "R", "G", "C"];

/**
 * What a land taps for, as symbols.
 *
 * Read from the server's `produces`, which is the union across the card's real
 * mana abilities. Subtypes would cover the five basics and nothing else; oracle
 * text would mean parsing rules text in the browser, which is the guess
 * `logic/mana.ts` refuses to make on the player's behalf.
 *
 * Note this is a *colour* answer, not an amount: "Add {G} or {U}" and
 * "Add {G}{U}" both come back as ["U", "G"]. `ManaView.sources` owns amounts.
 */
export function landSymbols(card: CardView): string[] {
  if (!card.types.includes("Land")) return [];
  return (card.produces ?? []).filter((symbol) => COLOR_SYMBOLS.includes(symbol));
}

/**
 * The body tint for a land: its colour, or `multi` for anything that makes more
 * than one. Null for non-lands and for a land that taps for nothing, both of
 * which keep the neutral `face--type-land` stock.
 *
 * Colourless is a tone of its own rather than falling back to the default,
 * because a Wastes and a creature-land that makes nothing should not look alike.
 */
export function landTone(card: CardView): LandTone | null {
  const symbols = landSymbols(card);
  if (symbols.length === 0) return null;
  if (symbols.length > 1) return "multi";
  return symbols[0] as LandTone;
}

/**
 * True when the card's rules box says nothing but "tap me for mana".
 *
 * A basic land's oracle text is its mana ability and nothing else, so on a board
 * of twelve of them it is twelve copies of a line nobody reads. The watermark
 * replaces it. Scoped to Basic on purpose: a nonbasic that taps for mana *and*
 * does something keeps its text, and there is no reliable way to tell those
 * apart from the text itself.
 */
export function isPlainLand(card: CardView): boolean {
  return card.types.includes("Land") && (card.supertypes ?? []).includes("Basic");
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

export type SymbolToken =
  | { kind: "text"; value: string; key: string }
  | { kind: "symbol"; value: string; label: string; tone: string; key: string };

/** Symbols worth drawing as a pip. Anything else stays as text. */
const RENDERABLE = /^([WUBRGC]|\d+|X|T|Q|S|E)$/;

/** What a non-mana symbol draws as. Mana symbols draw as their own letter. */
const SYMBOL_LABELS: Record<string, string> = {
  T: "↷", // tap
  Q: "↶", // untap
  S: "❄", // snow
  E: "✦", // energy
};

/**
 * Split text into runs and mana symbols: "{T}: Add {G}." -> [{T}, ": Add ", {G}, "."].
 *
 * Used wherever notation appears outside a cost row -- rules boxes and action
 * labels -- so `{2}{G}` reads the same there as it does under a card's title.
 * Unrecognised braces are returned as text: this is a renderer, and inventing a
 * pip for a symbol the engine does not support would be worse than showing the
 * raw notation the player can at least look up.
 */
export function symbolTokens(text: string): SymbolToken[] {
  const tokens: SymbolToken[] = [];
  let cursor = 0;
  let index = 0;

  for (const match of text.matchAll(/\{([^}]*)\}/g)) {
    const at = match.index ?? 0;
    if (at > cursor) {
      tokens.push({ kind: "text", value: text.slice(cursor, at), key: `t${index++}` });
    }
    const symbol = match[1].toUpperCase();
    if (RENDERABLE.test(symbol)) {
      tokens.push({
        kind: "symbol",
        value: symbol,
        label: SYMBOL_LABELS[symbol] ?? symbol,
        tone: /^[WUBRGC]$/.test(symbol)
          ? symbol
          : symbol === "T" || symbol === "Q"
            ? "tap"
            : "generic",
        key: `s${index++}`,
      });
    } else {
      tokens.push({ kind: "text", value: match[0], key: `t${index++}` });
    }
    cursor = at + match[0].length;
  }

  if (cursor < text.length) {
    tokens.push({ kind: "text", value: text.slice(cursor), key: `t${index++}` });
  }
  return tokens;
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
