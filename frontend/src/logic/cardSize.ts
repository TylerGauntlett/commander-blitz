/**
 * How big a card is, everywhere.
 *
 * Card geometry used to be nine hard-coded pixel constants scattered across
 * nine components -- `OWN_CARD_W = 104`, `CARD_W = 146`, `PREVIEW_W = 236` and
 * so on -- each written straight into a `--card-w` inline style. That is why a
 * 2560px display showed exactly the same small cards a 1366px one did: a
 * `clamp()` on `:root` was powerless, because an inline style beats it.
 *
 * Now there is one fluid `--card-w-base` in theme.css and every zone is a
 * *ratio* of it. The ratios below are the old pixel values divided by 104, so
 * the board keeps precisely the proportions it had -- only the absolute size
 * moves, and it moves with the viewport.
 */

/** The base every ratio multiplies, when CSS cannot be consulted (jsdom). */
export const FALLBACK_BASE = 104;

/**
 * Zone ratios, as multiples of `--card-w-base`.
 *
 * Derived from the pixel constants they replace: hand 146/104, preview 236/104,
 * peek 150/104, stack 116/104, spotlight 190/104, command slot 108/104.
 */
export const CARD_SCALE = {
  own: 1,
  hand: 1.4,
  preview: 2.27,
  peek: 1.44,
  stack: 1.12,
  spotlight: 1.83,
  commandSlot: 1.04,
} as const;

export type CardZone = keyof typeof CARD_SCALE;

/**
 * Opponent card width, by how many of them there are.
 *
 * Three mats at full size wrap their lands onto several rows and outgrow the
 * row they sit in, so `.mat--compact .mat__lanes` starts scrolling and a
 * permanent ends up one scroll away in the zone you most need to survey.
 * Shrinking is the cheaper trade now that type fill, land colour and the type
 * glyph all survive small sizes far better than the 5.6px type line they
 * replaced.
 *
 * The three values are the old 82 / 72 / 60 px over the old 104px base.
 */
export function opponentCardScale(count: number): number {
  if (count >= 3) return 0.58;
  if (count === 2) return 0.69;
  return 0.79;
}

/**
 * A `--card-w` value for an inline style.
 *
 * Returns a `calc()` against the fluid base rather than a pixel string, so the
 * zone still tracks the viewport. This is the whole point of the refactor: an
 * inline `104px` is what made `--card-w` unresponsive in the first place.
 */
export function cardWidthVar(scale: number): string {
  return `calc(var(--card-w-base) * ${round(scale)})`;
}

/**
 * The same ratio as a real number, for the few places that must do arithmetic
 * in JavaScript -- the hand fan positions its slots absolutely, so it needs
 * pixels rather than a `calc()` string.
 */
export function cardWidthPx(base: number, scale: number): number {
  return base * scale;
}

/** Trim float noise so the emitted CSS stays readable in devtools. */
function round(value: number): number {
  return Math.round(value * 1000) / 1000;
}
