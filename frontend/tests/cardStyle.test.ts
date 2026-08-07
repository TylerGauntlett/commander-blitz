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
  typeGlyph,
  typeLabel,
  typeTone,
} from "../src/logic/cardStyle";
import { card } from "./fixtures";

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
