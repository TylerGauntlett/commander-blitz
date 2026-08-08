/**
 * The greyscale check, automated -- for a card that is now an illustration.
 *
 * This file used to guard an eight-step luminance ladder: card type was the
 * colour of the card stock, plus a matching `--type-ring` hairline, and ~200
 * lines here computed relative luminance off `cards.css` to prove the eight
 * tones stayed separable without colour. It also contained a suite called "the
 * art window must never cover the whole face", whose stated purpose was to fail
 * if anyone ever let the art bleed to the edge.
 *
 * The art bleeds to the edge now. That was a decision (see
 * docs/mockup-fidelity.md and the header of `cards.css`): a full-bleed
 * illustration identifies a card better than one of eight pale washes, and it
 * does it per card rather than per category. The ladder is gone, so the tests
 * that measured it are gone with it.
 *
 * What replaces them is the property the ladder was really a proxy for: **can
 * you read this card.** On a bleed face that reduces to two numbers -- how dark
 * the scrims are, and how thick the frame is -- plus the structural facts that
 * the art is actually full bleed and a land's symbols are actually on top of it.
 * Those are arithmetic, so they are asserted here; the rest is `e2e/greyscale.spec.ts`,
 * which reads resolved values in a real browser.
 *
 * Read from the stylesheet rather than from a constant so these test the thing
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
// Newlines normalised on the way in. A CRLF checkout is a real thing on Windows,
// and the selector matching below is line-anchored -- without this these tests
// pass or fail on git's autocrlf setting, which is the least useful signal a test
// can carry.
const CSS = readFileSync(resolve(process.cwd(), "src/styles/cards.css"), "utf-8").replace(
  /\r\n/g,
  "\n",
);

/**
 * The body of the first rule matching a selector, or null.
 *
 * Line-anchored on purpose: `.face` must not match `.face--big .face`, and
 * `.face__head` must not match `.face--type-land .face__head`. A selector
 * spanning several lines is written here with plain `\n` between its parts.
 */
function rule(selector: string): string | null {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const found = CSS.match(new RegExp(`(^|\\n)${escaped}\\s*\\{([^}]*)\\}`));
  return found ? found[2] : null;
}

/**
 * The alpha of the most opaque black stop in a gradient.
 *
 * Every scrim fades to `rgb(0 0 0 / 0)` at its far end, which is the look; what
 * matters for legibility is the other end, where the text sits.
 */
function peakAlpha(gradient: string): number {
  const alphas = [...gradient.matchAll(/rgb\([^)]*\/\s*([\d.]+)\s*\)/g)].map((m) =>
    Number(m[1]),
  );
  return alphas.length > 0 ? Math.max(...alphas) : 0;
}

/**
 * How dark a scrim has to be at its text end.
 *
 * Not a perceptual standard -- a floor. White text at 0.7 over the brightest
 * crop in `data/art` is readable; at 0.4 it is not, and the failure is invisible
 * on any card whose illustration happens to be dark. This is the number that
 * stops "let's make the scrims subtler" from silently costing the board its
 * legibility, which is the same job the luminance ladder used to do.
 */
const MIN_SCRIM = 0.7;

describe("the art", () => {
  it("bleeds to the frame", () => {
    // The inverse of this file's old `leaves a surround of the type tint`. The
    // art is the card; there is no window and no paper around it.
    const art = rule(".face__art");
    expect(art, ".face__art no longer exists").not.toBeNull();
    expect(art).toMatch(/position:\s*absolute/);
    expect(art).toMatch(/inset:\s*0/);
  });

  it("leaves no padding on the face for the art to sit inside", () => {
    // A reinstated padding would put the frame back and quietly undo the
    // direction without changing anything else that is asserted here.
    const face = rule(".face");
    expect(face, ".face rule not found").not.toBeNull();
    expect(face).toMatch(/padding:\s*0/);
  });

  it("clips the art rather than letting it escape the frame", () => {
    expect(rule(".face__art")).toMatch(/overflow:\s*hidden/);
  });

  it("draws the art under both scrims, not over them", () => {
    // Ordering is the entire reason the text is readable. `.face__art` is the
    // floor at 0; a land's symbols sit at 1; the scrims are at 2.
    expect(rule(".face__art")).toMatch(/z-index:\s*0/);
    expect(rule(".face__head")).toMatch(/z-index:\s*2/);
    expect(rule(".face__foot")).toMatch(/z-index:\s*2/);
  });

  it("keeps a land's mana symbols on top of the art", () => {
    // The channel that reads at 60px and survives greyscale. Losing it to the
    // illustration would cost more than the illustration gains.
    const marks = rule(".face__art .watermark-row,\n.face__watermark");
    expect(marks, "the watermark rule moved or was split").not.toBeNull();
    expect(marks).toMatch(/position:\s*absolute/);
    expect(marks).toMatch(/z-index:\s*1/);
  });
});

describe("the scrims", () => {
  it("gives the head and the foot a gradient each", () => {
    // Gradients, not flat rectangles: a hard-edged band reads as a caption
    // pasted onto a photograph rather than as part of the card.
    expect(rule(".face__head")).toMatch(/background:\s*linear-gradient/);
    expect(rule(".face__foot")).toMatch(/background:\s*linear-gradient/);
  });

  it("holds both scrims dark enough to carry white text", () => {
    // The assertion with teeth in this file. If a scrim is lightened, every
    // card still *looks* right on whatever art the person making the change was
    // looking at, and becomes unreadable on some other card's bright crop.
    for (const selector of [".face__head", ".face__foot"]) {
      const body = rule(selector);
      expect(body, `${selector} rule not found`).not.toBeNull();
      expect(
        peakAlpha(body ?? ""),
        `${selector}'s scrim is too light to carry text over an unknown crop`,
      ).toBeGreaterThanOrEqual(MIN_SCRIM);
    }
  });

  it("fades each scrim out rather than ending it on an edge", () => {
    for (const selector of [".face__head", ".face__foot"]) {
      expect(rule(selector), `${selector} does not fade to transparent`).toMatch(
        /rgb\(0 0 0 \/ 0\)/,
      );
    }
  });

  it("goes near-opaque behind the enlarged card's rules box", () => {
    // The preview rail's only job is showing rules text, so that one surface
    // trades some of the illustration for legibility. See `.face--big
    // .face__foot`.
    const body = rule(".face--big .face__foot");
    expect(body, ".face--big .face__foot rule not found").not.toBeNull();
    expect(peakAlpha(body ?? "")).toBeGreaterThanOrEqual(0.94);
  });

  it("shadows the text as well as scrimming behind it", () => {
    // Two defences, because the scrim thins towards the middle of the card and
    // a long name reaches into that fade.
    for (const selector of [".face__title", ".face__type", ".face__rules"]) {
      expect(rule(selector), `${selector} carries no text-shadow`).toMatch(/text-shadow:/);
    }
  });
});

describe("the frame", () => {
  it("floors the frame border", () => {
    // Colour identity lives on this border, and it hits a rounding cliff at pod
    // sizes: the smallest card in a four-player pod is ~51px, and 3.2% of that
    // rounds down to one device pixel.
    const border = CSS.match(/border:\s*max\(([\d.]+)px,\s*calc\(var\(--card-w\)/);
    expect(border, ".face's border is not floored").not.toBeNull();
    expect(Number(border?.[1])).toBeGreaterThanOrEqual(2);
  });

  it("gives every colour identity a two-stop tint", () => {
    // The gradient behind the art, which on a card with no printing is the
    // whole card. One stop would render flat and lose the sense of a frame.
    for (const tone of ["W", "U", "B", "R", "G", "C", "gold", "land"]) {
      const body = rule(`.face--${tone}`);
      expect(body, `.face--${tone} is not defined`).not.toBeNull();
      expect(body, `.face--${tone} has no --f-hi`).toMatch(/--f-hi:\s*#[0-9a-f]{6}/i);
      expect(body, `.face--${tone} has no --f-lo`).toMatch(/--f-lo:\s*#[0-9a-f]{6}/i);
    }
  });

  it("tints a land's frame by the colour it taps for", () => {
    // Every land was the same tan rectangle, so a lane of twelve could only be
    // read by reading names -- docs/playtest-feedback-02.md item 8.
    for (const tone of ["W", "U", "B", "R", "G", "C", "multi"]) {
      const body = rule(`.face--land-${tone}`);
      expect(body, `.face--land-${tone} is not defined`).not.toBeNull();
      expect(body).toMatch(/--f-hi:\s*#[0-9a-f]{6}/i);
      expect(body).toMatch(/--f-lo:\s*#[0-9a-f]{6}/i);
    }
  });

  it("no longer encodes card type as a colour", () => {
    // The guard on the decision itself. Re-adding `.face--type-*` fills would
    // put a pale wash back over the illustration and re-open a question
    // docs/mockup-fidelity.md records as closed -- so make that a deliberate
    // act rather than something that can be slipped back in.
    expect(CSS).not.toMatch(/\.face--type-\w+\s*\{/);
    expect(CSS).not.toMatch(/--type-ring(-w)?:/);
  });
});
