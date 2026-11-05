/**
 * How far a handheld shorter than the Deck is scaled to lay out at the Deck's height.
 *
 * The handheld layout is drawn in CSS pixels against a Steam Deck's 1280x800:
 * the floors (`logic/floors.ts`), the 96px card floor, the seat strip, the
 * tool row and the hand's reserve are all stated in px, and together they need
 * the Deck's height. A screen in the handheld band that is shorter than that --
 * a tablet or an unfolded phone held sideways, 700-odd px tall -- got the same
 * fixed pieces in less room, and the viewer's own row was what gave: the seat
 * panel and the lanes were clipped under the hand.
 *
 * Lowering the floors there would make a worse Deck, not a better tablet. A
 * touch device's CSS pixel is physically larger than a Deck's (about 160 to the
 * inch against the Deck's 216), so the Deck's layout drawn a little smaller on
 * one is still at least as large in the hand as it is on a Deck. So the page is
 * laid out at the Deck's height and the browser scales it to the screen, through
 * the viewport tag: every measurement, media query and pointer coordinate stays
 * in one consistent space, which a CSS `zoom` would not promise (ADR 0028).
 *
 * Pure: `state/viewportFit.ts` measures and writes the tag.
 */

import { layoutModeForSize } from "./breakpoints";

/** The height the handheld layout is drawn for: a Steam Deck's panel. */
export const HANDHELD_DESIGN_H = 800;

/** The tag `index.html` ships, and what a size that needs no scale gets back. */
export const NATURAL_VIEWPORT = "width=device-width, initial-scale=1.0, viewport-fit=cover";

/**
 * The scale for a viewport of this natural size, at scale 1.
 *
 * 1 unless the size is a handheld and shorter than the design height. A phone
 * keeps its own layout, which is written for its own size; a desktop has the
 * room. The result is never below `PHONE_MAX_H / HANDHELD_DESIGN_H`, because
 * anything shorter than the phone query is a phone.
 */
export function viewportScale(width: number, height: number): number {
  if (width <= 0 || height <= 0) return 1;
  if (layoutModeForSize(width, height) !== "handheld") return 1;
  if (height >= HANDHELD_DESIGN_H) return 1;
  return height / HANDHELD_DESIGN_H;
}

/**
 * The viewport tag's content for a natural size.
 *
 * The width is stated as well as the scale, because the two engines disagree
 * about `initial-scale` alone: Blink widens the layout viewport to match and
 * WebKit may keep `device-width`. An explicit width is honoured by both, and the
 * height follows from the screen's aspect -- which is the design height, by
 * construction of the scale.
 */
export function viewportContent(width: number, height: number): string {
  const scale = viewportScale(width, height);
  if (scale >= 1) return NATURAL_VIEWPORT;
  const layoutW = layoutWidth(width, height);
  return `width=${layoutW}, initial-scale=${roundUp(width / layoutW)}, viewport-fit=cover`;
}

/**
 * The layout width the tag asks for, rounded UP so the height it implies is at
 * least the design height rather than a pixel under it.
 */
export function layoutWidth(width: number, height: number): number {
  return Math.ceil(width / viewportScale(width, height));
}

/**
 * The scale is the one that fits the stated width to the screen, rounded UP.
 *
 * Down is the wrong way: a scale under `width / layoutW` would show more than
 * the layout is wide, which is below the engine's own minimum, and Blink then
 * drops the requested scale altogether and draws the wide layout at 1 -- the
 * page zoomed in, its right side off the screen.
 */
function roundUp(value: number): number {
  return Math.ceil(value * 10_000) / 10_000;
}
