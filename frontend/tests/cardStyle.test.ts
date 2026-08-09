/**
 * The two visual channels a card encodes: colour identity and card type.
 *
 * `frameTone` (border) and `typeTone` (body fill) are deliberately independent,
 * so the tests that matter are the ones proving they stay independent and that
 * neither collapses two things a player needs to tell apart.
 */

import { describe, expect, it } from "vitest";
import {
  type TypeTone,
  frameTone,
  isPlainLand,
  isWounded,
  landSymbols,
  landTone,
  shortType,
  symbolTokens,
  typeGlyph,
  typeLabel,
  typeTone,
} from "../src/logic/cardStyle";
import { card } from "./fixtures";

/** A land as the server sends one: types, supertypes, and what it taps for. */
function land(overrides: Parameters<typeof card>[0] = {}) {
  return card({
    types: ["Land"],
    supertypes: ["Basic"],
    produces: ["U"],
    mana_cost: "",
    colors: [],
    power: null,
    toughness: null,
    ...overrides,
  });
}

describe("typeTone", () => {
  it.each([
    [["Creature"], "creature"],
    [["Land"], "land"],
    [["Artifact"], "artifact"],
    [["Enchantment"], "enchantment"],
    [["Instant"], "instant"],
    [["Sorcery"], "sorcery"],
    [["Planeswalker"], "planeswalker"],
  ])("maps %s to %s", (types, expected) => {
    expect(typeTone(card({ types }))).toBe(expected);
  });

  it("falls back to 'other' for a type it has never seen", () => {
    expect(typeTone(card({ types: ["Conspiracy"] }))).toBe("other");
    expect(typeTone(card({ types: [] }))).toBe("other");
  });

  describe("precedence", () => {
    it("reads an artifact creature as a creature", () => {
      // What it does beats what it is made of: this thing attacks and blocks.
      expect(typeTone(card({ types: ["Artifact", "Creature"] }))).toBe("creature");
    });

    it("reads an enchantment creature as a creature", () => {
      expect(typeTone(card({ types: ["Enchantment", "Creature"] }))).toBe("creature");
    });

    it("reads a creature land as a land", () => {
      // Matches frameTone, which also lets Land win outright.
      expect(typeTone(card({ types: ["Land", "Creature"] }))).toBe("land");
    });

    it("does not depend on the order the server lists types in", () => {
      expect(typeTone(card({ types: ["Creature", "Artifact"] }))).toBe(
        typeTone(card({ types: ["Artifact", "Creature"] })),
      );
    });
  });
});

describe("the two channels stay independent", () => {
  it("gives a green creature and a green instant the same border, different bodies", () => {
    const creature = card({ types: ["Creature"], colors: ["G"] });
    const instant = card({ types: ["Instant"], colors: ["G"] });
    expect(frameTone(creature)).toBe(frameTone(instant));
    expect(typeTone(creature)).not.toBe(typeTone(instant));
  });

  it("gives a red creature and a green creature the same body, different borders", () => {
    const red = card({ types: ["Creature"], colors: ["R"] });
    const green = card({ types: ["Creature"], colors: ["G"] });
    expect(typeTone(red)).toBe(typeTone(green));
    expect(frameTone(red)).not.toBe(frameTone(green));
  });

  it("separates instant from sorcery, which is half of 'why can't I play this'", () => {
    expect(typeTone(card({ types: ["Instant"] }))).not.toBe(
      typeTone(card({ types: ["Sorcery"] })),
    );
  });
});

describe("typeGlyph", () => {
  const tones: TypeTone[] = [
    "creature",
    "land",
    "artifact",
    "enchantment",
    "instant",
    "sorcery",
    "planeswalker",
    "other",
  ];

  it("gives every tone a distinct glyph", () => {
    // The doc's greyscale check: if two types share a mark, the encoding is
    // colour-only and the glyph is doing no work.
    const glyphs = tones.map((tone) =>
      typeGlyph(card({ types: [tone === "other" ? "Conspiracy" : capitalise(tone)] })),
    );
    expect(new Set(glyphs).size).toBe(tones.length);
  });

  it("is a single character, so it never reflows the title bar", () => {
    for (const tone of tones) {
      const glyph = typeGlyph(
        card({ types: [tone === "other" ? "Conspiracy" : capitalise(tone)] }),
      );
      expect([...glyph]).toHaveLength(1);
    }
  });

  it("uses no emoji, which would render as colour fonts at inconsistent widths", () => {
    for (const tone of tones) {
      const glyph = typeGlyph(
        card({ types: [tone === "other" ? "Conspiracy" : capitalise(tone)] }),
      );
      expect(glyph.codePointAt(0)).toBeLessThan(0x1f000);
    }
  });
});

describe("typeLabel", () => {
  it("names the type for the tooltip", () => {
    expect(typeLabel(card({ types: ["Creature"] }))).toBe("Creature");
    expect(typeLabel(card({ types: ["Land"] }))).toBe("Land");
  });

  it("says 'Card' rather than 'Other' for an unknown type", () => {
    expect(typeLabel(card({ types: [] }))).toBe("Card");
  });
});

function capitalise(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1);
}

/**
 * The third channel, added in cycle 3: what a land taps for.
 *
 * Every land used to be the same tan rectangle, so a lane of twelve of them
 * could only be read by reading names. The answer comes from the server's
 * `produces` -- the union across the card's real mana abilities -- because a
 * subtype covers the five basics and nothing else, and parsing oracle text in
 * the browser is the guess `logic/mana.ts` refuses to make.
 */
describe("landSymbols", () => {
  it.each([
    [["W"], "Plains"],
    [["U"], "Island"],
    [["B"], "Swamp"],
    [["R"], "Mountain"],
    [["G"], "Forest"],
  ])("reads %s off a %s", (produces) => {
    expect(landSymbols(land({ produces }))).toEqual(produces);
  });

  it("keeps every colour a dual can make", () => {
    expect(landSymbols(land({ produces: ["U", "G"], supertypes: [] }))).toEqual(["U", "G"]);
  });

  it("says nothing about a non-land, whatever it taps for", () => {
    // A mana creature produces {G}, but the body fill is already saying
    // "creature" and must not start claiming to be a Forest.
    expect(landSymbols(card({ types: ["Creature"], produces: ["G"] }))).toEqual([]);
  });

  it("ignores symbols that are not colours", () => {
    expect(landSymbols(land({ produces: ["U", "2", ""] }))).toEqual(["U"]);
  });

  it("tolerates a payload from before the field existed", () => {
    expect(landSymbols(land({ produces: undefined as unknown as string[] }))).toEqual([]);
  });
});

describe("landTone", () => {
  it("gives a mono land its own colour", () => {
    expect(landTone(land({ produces: ["R"] }))).toBe("R");
  });

  it("calls anything with a choice 'multi' rather than picking one", () => {
    // Two solid colours would claim the land is both, which is the same
    // overstatement the split mana pip exists to avoid.
    expect(landTone(land({ produces: ["U", "G"] }))).toBe("multi");
  });

  it("keeps colourless distinct from produces-nothing", () => {
    // A Wastes and a creature-land that taps for nothing should not look alike.
    expect(landTone(land({ produces: ["C"] }))).toBe("C");
    expect(landTone(land({ produces: [] }))).toBeNull();
  });

  it("is null for a non-land, which keeps its type fill", () => {
    expect(landTone(card({ types: ["Creature"], produces: ["G"] }))).toBeNull();
  });

  it("does not disturb the border, which still carries colour identity", () => {
    // The two channels stay independent: a Forest is a land frame that happens
    // to be tinted green, not a green card.
    const forest = land({ produces: ["G"], colors: [] });
    expect(landTone(forest)).toBe("G");
    expect(frameTone(forest)).toBe("land");
  });
});

describe("isPlainLand", () => {
  it("is true for a basic, whose rules text is only its mana ability", () => {
    expect(isPlainLand(land({ supertypes: ["Basic"] }))).toBe(true);
  });

  it("is false for a nonbasic, which may say something worth reading", () => {
    // Scoped to Basic deliberately: a land that taps for mana *and* does
    // something is exactly the card you need the text of.
    expect(isPlainLand(land({ supertypes: [] }))).toBe(false);
  });

  it("is false for anything that is not a land", () => {
    expect(isPlainLand(card({ types: ["Creature"], supertypes: ["Basic"] }))).toBe(false);
  });
});

describe("isWounded", () => {
  it("is true for a damaged permanent", () => {
    expect(isWounded(card({ zone: "battlefield", damage: 2 }))).toBe(true);
  });

  it("is false with no damage marked", () => {
    expect(isWounded(card({ zone: "battlefield", damage: 0 }))).toBe(false);
    expect(isWounded(card({ zone: "battlefield", damage: undefined }))).toBe(false);
  });

  it("is false off the battlefield, where damage does not exist", () => {
    expect(isWounded(card({ zone: "graveyard", damage: 3 }))).toBe(false);
  });
});

/**
 * Mana notation outside a cost row.
 *
 * A card's casting cost has been coloured pips since cycle 1, but rules text and
 * action labels still spelled the same notation out as "{T}: Add {G}." -- two
 * renderings of one thing on one screen, one of which needs decoding.
 */
describe("symbolTokens", () => {
  it("splits text around its symbols", () => {
    const tokens = symbolTokens("{T}: Add {G}.");
    expect(tokens.map((t) => t.kind)).toEqual(["symbol", "text", "symbol", "text"]);
    expect(tokens.filter((t) => t.kind === "symbol").map((t) => t.value)).toEqual(["T", "G"]);
  });

  it("returns plain text untouched, as one run", () => {
    const tokens = symbolTokens("Flying, trample");
    expect(tokens).toHaveLength(1);
    expect(tokens[0]).toMatchObject({ kind: "text", value: "Flying, trample" });
  });

  it("handles an empty string", () => {
    expect(symbolTokens("")).toEqual([]);
  });

  it("colours mana symbols by their own letter", () => {
    const tokens = symbolTokens("{2}{G}{U}");
    expect(tokens.map((t) => (t.kind === "symbol" ? t.tone : null))).toEqual([
      "generic",
      "G",
      "U",
    ]);
  });

  it("draws tap and untap as glyphs rather than letters", () => {
    // "{T}" as the letter T next to "{2}" reads as a mana symbol it is not.
    const [tap] = symbolTokens("{T}");
    expect(tap).toMatchObject({ kind: "symbol", value: "T", label: "↷", tone: "tap" });
    const [untap] = symbolTokens("{Q}");
    expect(untap).toMatchObject({ value: "Q", label: "↶", tone: "tap" });
  });

  it("keeps multi-digit generic costs as one symbol", () => {
    const [pip] = symbolTokens("{10}");
    expect(pip).toMatchObject({ kind: "symbol", value: "10", label: "10" });
  });

  it("draws hybrid and phyrexian symbols", () => {
    // These used to fall back to text, on the grounds that the engine rejects
    // hybrid costs at load time so none could reach the screen. Deck import
    // changed that: a generated card's oracle text is shown verbatim and its
    // activation costs are full of them, so `public/symbols/` carries all 24.
    expect(symbolTokens("{G/U} hybrid")[0]).toMatchObject({
      kind: "symbol",
      value: "G/U",
      tone: "G",
    });
    expect(symbolTokens("{2/W}")[0]).toMatchObject({ kind: "symbol", value: "2/W", tone: "W" });
    expect(symbolTokens("{U/P}")[0]).toMatchObject({ kind: "symbol", value: "U/P", tone: "U" });
  });

  it("leaves notation it does not recognise as text rather than guessing", () => {
    // Inventing a pip for a symbol there is no SVG for is worse than showing
    // the raw notation, which a player can at least look up.
    const tokens = symbolTokens("{HW} half");
    expect(tokens[0]).toMatchObject({ kind: "text", value: "{HW}" });
  });

  it("gives every token a distinct key, including repeats", () => {
    const keys = symbolTokens("{G}{G}{G}").map((t) => t.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("preserves the sentence when the tokens are joined back up", () => {
    const text = "{2}, {T}, Sacrifice: Search your library for a basic land.";
    const rebuilt = symbolTokens(text)
      .map((t) => (t.kind === "text" ? t.value : `{${t.value}}`))
      .join("");
    expect(rebuilt).toBe(text);
  });
});

describe("shortType", () => {
  it("drops a supertype the card already says another way", () => {
    // `Legendary` is said by the crown in the name, so on a board card the line
    // spends itself on the subtype instead.
    expect(shortType("Legendary Creature - Human Merfolk")).toBe("Creature - Human Merfolk");
    expect(shortType("Basic Land - Forest")).toBe("Land - Forest");
    expect(shortType("Token Creature - Elemental")).toBe("Creature - Elemental");
  });

  it("drops two, because a card can have two", () => {
    expect(shortType("Legendary Snow Creature - Yeti")).toBe("Creature - Yeti");
  });

  it("leaves a line with no supertype alone", () => {
    expect(shortType("Creature - Ooze")).toBe("Creature - Ooze");
    expect(shortType("Instant")).toBe("Instant");
    expect(shortType("Land")).toBe("Land");
  });

  it("never empties the line", () => {
    // `e2e/greyscale.spec.ts` asserts every face carries a type line, because
    // with the type-colour ladder gone this and the glyph are what is left.
    for (const line of ["Legendary Creature - Serpent", "Basic Land - Island", "Artifact"]) {
      expect(shortType(line).length).toBeGreaterThan(0);
    }
  });

  it("does not eat a subtype that happens to be a supertype word", () => {
    // Only a *leading* run comes off. "Creature - Legendary" is not a real card,
    // but the anchoring is the property worth pinning.
    expect(shortType("Enchantment - Snow")).toBe("Enchantment - Snow");
  });
});
