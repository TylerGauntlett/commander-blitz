/**
 * The greyscale check, automated.
 *
 * Both playtest docs asked for a greyscale legibility check and both concluded
 * it "has no automated form -- a `grayscale(1)` screenshot has to be read by
 * someone". That is true of *layout*. It is not true of the palette: greyscale
 * legibility is relative luminance, which is arithmetic.
 *
 * Cycle 2's seven type fills all sat at L~88%, so a monochrome display, a
 * strongly colour-deficient viewer, or a card half-occluded in a stack ply all
 * reduced to one small glyph. Cycle 3 spread them. These tests are what stop a
 * future "let's warm up the artifact blue" from quietly collapsing the spread
 * again -- the failure is invisible in colour, which is exactly why a person
 * looking at a screenshot would miss it.
 *
 * Read from the stylesheet rather than from a constant so they test the thing
 * that actually ships.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// Read off disk rather than imported. `import ... from "...css?raw"` returns an
// empty string under vitest, which stubs CSS modules out, and `import.meta.url`
// is an http: URL in jsdom rather than a path -- so the vitest root is the one
// reliable anchor. Reading the shipped file is also the point: the test must
// fail when `cards.css` changes, not when a copy of its values does.
const CSS = readFileSync(resolve(process.cwd(), "src/styles/cards.css"), "utf-8");

/** `.face--type-land { --stock: #d6c7a8; ... }` -> { land: "#d6c7a8" } */
function stocks(prefix: string): Record<string, string> {
  const found: Record<string, string> = {};
  const rule = new RegExp(`\\.face--${prefix}-([\\w]+)\\s*\\{([^}]*)\\}`, "g");
  for (const [, name, body] of CSS.matchAll(rule)) {
    const stock = body.match(/--stock:\s*(#[0-9a-fA-F]{6})/);
    if (stock) found[name] = stock[1];
  }
  return found;
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** WCAG relative luminance: what a greyscale display would show. */
function luminance(hex: string): number {
  const n = Number.parseInt(hex.slice(1), 16);
  const r = channel((n >> 16) & 255);
  const g = channel((n >> 8) & 255);
  const b = channel(n & 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/**
 * `.card--dimmed` composites `rgb(8 16 12 / 0.22)` over the stock.
 *
 * Kept in sync with cards.css by `parses the dimming scrim out of the CSS`
 * below, so a change to the scrim fails here rather than silently invalidating
 * the headroom the palette was tuned against.
 */
function dimmed(hex: string): string {
  const n = Number.parseInt(hex.slice(1), 16);
  const over = [8, 16, 12];
  const out = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c, i) =>
    Math.round(0.78 * c + 0.22 * over[i]),
  );
  return `#${out.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

const typeTones = stocks("type");
const landTones = stocks("land");

/**
 * The minimum luminance step between two tones.
 *
 * 0.03 is not a perceptual standard, it is a floor: cycle 2's palette had a
 * worst-case gap of ~0.002, which is indistinguishable. The shipped spread
 * clears 0.04.
 */
const MIN_GAP = 0.03;

describe("the type palette", () => {
  it("defines a stock for all eight type tones", () => {
    expect(Object.keys(typeTones).sort()).toEqual([
      "artifact",
      "creature",
      "enchantment",
      "instant",
      "land",
      "other",
      "planeswalker",
      "sorcery",
    ]);
  });

  it("separates every pair of tones in greyscale", () => {
    const sorted = Object.entries(typeTones)
      .map(([name, hex]) => [name, luminance(hex)] as const)
      .sort((a, b) => a[1] - b[1]);

    for (let i = 1; i < sorted.length; i += 1) {
      const [lower, low] = sorted[i - 1];
      const [upper, high] = sorted[i];
      expect(
        high - low,
        `${lower} and ${upper} are indistinguishable without colour`,
      ).toBeGreaterThan(MIN_GAP);
    }
  });

  it("keeps land darkest and the neutral stock lightest", () => {
    // Land and creature are most of a board, so they sit at the two ends of the
    // useful range rather than next to each other.
    const byLuminance = Object.entries(typeTones).sort(
      (a, b) => luminance(a[1]) - luminance(b[1]),
    );
    expect(byLuminance[0][0]).toBe("land");
    expect(byLuminance[byLuminance.length - 1][0]).toBe("other");
  });

  it("never lets a dark type read as a dimmed one", () => {
    // The constraint docs/playtest-feedback-02.md set on widening the range: the
    // whole dimmed band must sit below the whole undimmed band, or an undimmed
    // land is darker than a dimmed instant and reads as unplayable.
    const all = Object.values({ ...typeTones, ...landTones });
    const darkestLive = Math.min(...all.map(luminance));
    const lightestDimmed = Math.max(...all.map((hex) => luminance(dimmed(hex))));
    expect(darkestLive).toBeGreaterThan(lightestDimmed);
  });

  it("parses the dimming scrim out of the CSS", () => {
    // If this fails the scrim moved and `dimmed()` above is now a fiction, which
    // would make the headroom test pass for the wrong reason.
    expect(CSS).toContain("background: rgb(8 16 12 / 0.22);");
  });

  it("gives every type tone a darker second stop", () => {
    // `.face` is a gradient between --stock and --stock-shade; equal stops would
    // render flat and lose the card's sense of a printed surface.
    const rule = /\.face--type-\w+\s*\{([^}]*)\}/g;
    for (const [, body] of CSS.matchAll(rule)) {
      const top = body.match(/--stock:\s*(#[0-9a-fA-F]{6})/);
      const shade = body.match(/--stock-shade:\s*(#[0-9a-fA-F]{6})/);
      expect(top).not.toBeNull();
      expect(shade).not.toBeNull();
      if (top && shade) {
        expect(luminance(shade[1])).toBeLessThan(luminance(top[1]));
      }
    }
  });
});

describe("the land palette", () => {
  it("defines a stock for each colour a land can make", () => {
    expect(Object.keys(landTones).sort()).toEqual(["B", "C", "G", "R", "U", "W", "multi"]);
  });

  it("holds every land at one luminance", () => {
    // Deliberately flat. Lightness is spoken for by card *type*; if an Island
    // were lighter than a Mountain the board would be claiming they are
    // different kinds of card. Hue separates them, and the watermark letter
    // separates them for anyone who cannot use hue.
    const values = Object.values(landTones).map(luminance);
    expect(Math.max(...values) - Math.min(...values)).toBeLessThan(0.015);
  });

  it("sits at the land band, not somewhere else on the type scale", () => {
    const base = luminance(typeTones.land);
    for (const [name, hex] of Object.entries(landTones)) {
      expect(Math.abs(luminance(hex) - base), `${name} drifted off the land band`).toBeLessThan(
        0.02,
      );
    }
  });

  it("stays clear of the next type tone up", () => {
    // A tinted land must not climb into creature territory: it would read as the
    // wrong card type, which is a worse error than being the wrong colour.
    const creature = luminance(typeTones.creature);
    for (const hex of Object.values(landTones)) {
      expect(creature - luminance(hex)).toBeGreaterThan(MIN_GAP);
    }
  });
});
