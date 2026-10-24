/**
 * The legibility checks, as page functions both specs share.
 *
 * `legibility.spec.ts` asks them of the desktop board and `phone.spec.ts` of
 * every phone held both ways (ADR 0025), so "can you read a card" is one
 * question at every size. Each runs in the page and closes over nothing,
 * because `page.evaluate` sends the function alone.
 */

/**
 * How dark a scrim has to be at the end the text sits on.
 *
 * The same floor `tests/palette.test.ts` parses out of the stylesheet, checked
 * here against what the browser actually resolved. White type at 0.7 is
 * readable over the brightest crop in `data/art`; below that it depends on
 * which card you happen to be looking at, which is not a property.
 */
export const MIN_SCRIM = 0.7;

/** The thinnest a card's frame may be and still read as a line. */
export const MIN_FRAME = 1.5;

/** Every card text band whose scrim peaks under `floor`. */
export function scrimFailures(floor: number): string[] {
  /** The most opaque black stop in a resolved `linear-gradient(...)`. */
  const peak = (background: string) => {
    const stops = [...background.matchAll(/rgba?\(([^)]*)\)/g)].map((m) =>
      m[1].split(/[,/]/).map((n) => Number.parseFloat(n.trim())),
    );
    const alphas = stops
      // Only the dark stops count: a scrim is black fading to nothing, and
      // the transparent end is the look rather than the legibility.
      .filter((c) => c.length >= 3 && c[0] < 60 && c[1] < 60 && c[2] < 60)
      .map((c) => (c.length >= 4 ? c[3] : 1));
    return alphas.length > 0 ? Math.max(...alphas) : 0;
  };

  const failures: string[] = [];
  for (const face of document.querySelectorAll<HTMLElement>(".face")) {
    const name = face.dataset.cardName ?? "?";
    for (const part of ["face__head", "face__foot"]) {
      const band = face.querySelector<HTMLElement>(`.${part}`);
      if (!band) {
        failures.push(`${name}: no .${part}`);
        continue;
      }
      const alpha = peak(getComputedStyle(band).backgroundImage);
      if (alpha < floor) failures.push(`${name}: .${part} peaks at ${alpha}`);
    }
  }
  return failures;
}

/** The frame width of every drawn face, in CSS pixels. */
export function frameWidths(selector: string): number[] {
  return [...document.querySelectorAll<HTMLElement>(selector)].map((face) =>
    Number.parseFloat(getComputedStyle(face).borderTopWidth),
  );
}
