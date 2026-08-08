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

/**
 * `.face--type-land { --stock: #d6c7a8; ... }` -> { land: "#d6c7a8" }
 *
 * Generalised over the property so the same parser reads `--stock` and
 * `--type-ring`, which are set side by side in the same rules.
 */
function props(prefix: string, property: string): Record<string, string> {
  const found: Record<string, string> = {};
  const rule = new RegExp(`\\.face--${prefix}-([\\w]+)\\s*\\{([^}]*)\\}`, "g");
  const value = new RegExp(`${property}:\\s*(#[0-9a-fA-F]{6})`);
  for (const [, name, body] of CSS.matchAll(rule)) {
    const hit = body.match(value);
    if (hit) found[name] = hit[1];
  }
  return found;
}

function stocks(prefix: string): Record<string, string> {
  return props(prefix, "--stock");
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

/**
 * The type ring: what still says "this is a creature" once art covers the paper.
 *
 * The `--stock` ladder above is intact and still does real work -- it colours
 * the title bar, the type line, the footer, and the whole of a card that has no
 * printing. But art occupies most of the face now, and mockups/README.md is
 * right that the fill alone cannot survive that. The ring is the answer: a
 * hairline at the frame's inner edge, drawn *over* the art, keyed on the same
 * eight type tones.
 *
 * These are the assertions with teeth. If the ring collapses, a board in
 * greyscale becomes a wall of indistinguishable tiles again, and nothing about
 * the colour rendering will look wrong.
 */
describe("the type ring", () => {
  const typeRings = props("type", "--type-ring");

  it("defines a ring for every type tone", () => {
    // The guard that makes forgetting impossible: add a type fill without a
    // ring and this fails, rather than the card quietly losing its encoding.
    expect(Object.keys(typeRings).sort()).toEqual(Object.keys(typeTones).sort());
  });

  it("separates every pair of rings in greyscale", () => {
    const sorted = Object.entries(typeRings)
      .map(([name, hex]) => [name, luminance(hex)] as const)
      .sort((a, b) => a[1] - b[1]);

    for (let i = 1; i < sorted.length; i += 1) {
      const [lower, low] = sorted[i - 1];
      const [upper, high] = sorted[i];
      expect(
        high - low,
        `the ${lower} and ${upper} rings are indistinguishable without colour`,
      ).toBeGreaterThan(MIN_GAP);
    }
  });

  it("orders the rings the same way as the fills", () => {
    // Two channels saying different things about the same card is worse than
    // one channel saying nothing, so the ladders must agree.
    const byLuminance = (tones: Record<string, string>) =>
      Object.entries(tones)
        .sort((a, b) => luminance(a[1]) - luminance(b[1]))
        .map(([name]) => name);
    expect(byLuminance(typeRings)).toEqual(byLuminance(typeTones));
  });

  it("spans a wide enough band to be read at three pixels", () => {
    // A first attempt held every ring below L 0.35, reasoning that a light ring
    // would be lost against a light art crop. That squeezed all eight into the
    // bottom of the range with ~0.04 between them, and two dark browns are not
    // tellable apart on a 3px line. The dark edge drawn inside the ring solves
    // that problem instead, which frees the ladder to spread.
    const values = Object.values(typeRings).map(luminance);
    expect(Math.max(...values) - Math.min(...values)).toBeGreaterThan(0.45);
  });

  it("draws a dark edge inside the ring", () => {
    // What lets the ring be light. Without it a pale instant ring on a pale
    // illustration disappears, and the spread above becomes a liability.
    expect(CSS).toMatch(/inset 0 0 0\s+calc\(var\(--type-ring-w\) \+ [\d.]+px\) rgb\(0 0 0/);
  });

  it("keeps the ring wide enough to survive the art", () => {
    // Where a visual property reduces to a number, assert the number --
    // otherwise "let's make it subtler" quietly reverts this to a hairline and
    // every other test here still passes.
    const width = CSS.match(
      /--type-ring-w:\s*max\(([\d.]+)px,\s*calc\(var\(--card-w\)\s*\*\s*([\d.]+)\)\)/,
    );
    expect(width, "--type-ring-w is not a floored ratio of --card-w").not.toBeNull();
    expect(Number(width?.[2])).toBeGreaterThanOrEqual(0.03);
    // The floor matters more than the ratio. The smallest card in a pod is
    // ~51px, and 3.4% of that rounds down to one device pixel -- at which
    // point the ring stops being a colour and becomes an artefact.
    expect(Number(width?.[1])).toBeGreaterThanOrEqual(2);
  });

  it("floors the frame border too", () => {
    // Colour identity lives on the outer border and hits the same rounding
    // cliff at pod sizes.
    const border = CSS.match(/border:\s*max\(([\d.]+)px,\s*calc\(var\(--card-w\)/);
    expect(border, ".face's border is not floored").not.toBeNull();
    expect(Number(border?.[1])).toBeGreaterThanOrEqual(2);
  });
});

/**
 * The art window must never cover the whole face.
 *
 * `.face`'s padding is the band of type-tinted paper left showing all the way
 * round the art. It is the second half of the greyscale argument -- the ring is
 * the first -- and it is exactly what a future "let the art bleed to the edge"
 * change would remove without anything else noticing.
 */
describe("the art window", () => {
  it("leaves a surround of the type tint", () => {
    const padding = CSS.match(
      /\.face \{[^}]*padding:\s*calc\(var\(--card-w\)\s*\*\s*([\d.]+)\)/,
    );
    expect(padding, ".face no longer declares padding as a ratio of --card-w").not.toBeNull();
    expect(Number(padding?.[1])).toBeGreaterThan(0);
  });

  it("clips the art rather than letting it escape the frame", () => {
    expect(CSS).toMatch(/\.face__art \{[^}]*overflow:\s*hidden/);
  });

  it("caps the art on a face that also shows rules text", () => {
    // Without the cap the band takes the remaining height and squeezes the
    // rules box to nothing -- which is the hand and the preview, the two
    // places the text is the whole point.
    expect(CSS).toMatch(/\.face--detail \.face__art \{[^}]*aspect-ratio/);
  });

  it("keeps a land's mana symbols on top of the art", () => {
    // The channel that reads at 60px and survives greyscale. Losing it to the
    // illustration would cost more than the illustration gains.
    expect(CSS).toMatch(/\.face__art \.watermark-row \{[^}]*position:\s*absolute/);
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
