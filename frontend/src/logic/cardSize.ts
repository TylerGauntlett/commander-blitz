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
 * The narrowest card the board may ever render.
 *
 * Not a taste call. `cards.css` clamps its type sizes at both ends, and the 8.5px
 * floors on `--fs-tp` and `--fs-tx` stop binding at about a 137px card -- so below
 * that the text has already stopped shrinking and every further pixel taken off
 * the card is pure crowding. Meanwhile 50.7px (`opponentCardScale(3)` against an
 * 87.4px base) is the smallest width the suite has *demonstrated* still reads:
 * `e2e/legibility.spec.ts` measures a three-opponent pod at exactly that size.
 *
 * So this is that size, rounded up: the zoom may go as small as something we have
 * checked is readable, and no smaller.
 */
export const MIN_CARD_W = 52;

/**
 * The floor on a handheld, from `mockups/handheld/assert.js`'s `CARD_FLOOR`.
 *
 * Any card the focus ring can land on must be at least this wide. It is derived
 * from a 7-inch panel at 40-50cm rather than from a DPI number: below about
 * 96px a card's illustration stops identifying it and its stats stop being
 * readable, which makes the board a list of rectangles.
 *
 * At 96 a full board will not always fit the viewport. That is a deliberate
 * trade rather than a bug -- `.play__mine` already scrolls, and a board you
 * have to scroll is worth more than a board you cannot read.
 */
export const HANDHELD_MIN_CARD_W = 96;

/**
 * The widest, and the reason is a hierarchy rather than a limit.
 *
 * `.face--big` in `cards.css` pins the preview rail's card to 150px and says
 * plainly that the width is a fiction -- the box is as wide as the rail. That
 * fiction sets the type scale of *the panel you read cards in*. A board card wider
 * than it would render its name, type line and P/T larger than the preview does,
 * so the board would out-shout the thing whose whole job is to be the readable
 * copy.
 *
 * Capping here also keeps every `--fs-*` clamp in its linear range: `--pip` first
 * hits its ceiling at about 182px and `--fs-tp` at 202px. The ceilings stay
 * unbound backstops, which is what `cards.css` says they are for.
 *
 * The pod lobby's card is wider than this -- up to 296px -- and renders its name
 * at 13.9px against the rail's 13.5px. That does not break the hierarchy above,
 * because the hierarchy is about *one screen*: the board and the preview rail
 * share a viewport and compete for the same eye, while the lobby and the table
 * are never on screen together. It is the same argument `docs/mockup-fidelity.md`
 * makes for the lobby keeping its own `.podcard` box.
 */
export const MAX_CARD_W = 150;

/**
 * Zone ratios, as multiples of `--card-w-base`.
 *
 * Derived from the pixel constants they replace: hand 146/104, preview 236/104,
 * peek 150/104, stack 116/104, spotlight 190/104, command slot 108/104.
 *
 * **`own`, `hand` and `opponentCardScale` are now ceilings, not sizes.** The
 * values have not changed, but progressive zoom (see `zoomFit.ts` and
 * `state/useZoomFit.ts`) solves the board and the hand against the space actually
 * available and may return anything from `MIN_CARD_W` up to these. They are what
 * the zoom is not allowed to exceed -- the size the board was playtested at, kept
 * as the upper bound so growth is opt-in on displays that have the room and never
 * a surprise on the ones that do not. Every other entry here is still a fixed
 * ratio; nothing zooms the preview, the peek or the spotlight.
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
 *
 * The zoom rides in the same `scale`, which is deliberate: there is one
 * coefficient per zone and both languages read it, so a zoom that CSS knows about
 * and JavaScript does not cannot happen. **A `scale` is always absolute against
 * `--card-w-base` -- nothing multiplies one twice, and `cardWidthVar(s)` and
 * `cardWidthPx(base, s)` must always be handed the same `s`.**
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
