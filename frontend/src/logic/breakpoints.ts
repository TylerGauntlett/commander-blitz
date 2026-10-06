/**
 * Where the table stops being a desktop board and becomes a handheld one.
 *
 * ONE STRING, AND BOTH CONSUMERS READ IT. `styles/handheld.css` uses the media
 * query literally; this module hands the identical text to `matchMedia`. The
 * two cannot be allowed to drift, because they answer the same question in
 * different languages and a disagreement is invisible -- CSS would compact the
 * rails while React kept rendering the left one, or the reverse.
 *
 * `tests/breakpoints.test.ts` reads the stylesheet off disk and asserts it
 * contains this exact string. That is a cheaper guarantee than any amount of
 * care, and it is the only reason it is safe to state the query twice.
 *
 * WHY BOTH A QUERY AND A FLAG. CSS alone cannot do this job: the handheld
 * layout moves the log and the stack into overlays, and a media query cannot
 * move a component into a different parent. So React needs the boolean, and
 * `matchMedia` is how it gets it without inventing a second definition.
 *
 * THE NUMBERS. A Steam Deck is 1280x800. 1366 is the widest common laptop panel
 * below the 1600x950 the suites are written at, and 820 catches a 1280x800
 * window that has grown some browser chrome. Either dimension is enough on its
 * own -- a short wide window is as hostile to a three-row table as a narrow one
 * is to three columns.
 */

export const HANDHELD_MAX_W = 1366;
export const HANDHELD_MAX_H = 820;

/** The media query, as both stylesheets and `matchMedia` see it. */
export const HANDHELD_QUERY = `(max-width: ${HANDHELD_MAX_W}px), (max-height: ${HANDHELD_MAX_H}px)`;

/**
 * Whether the viewport wants the handheld layout right now.
 *
 * Defaults to `false` where `matchMedia` does not exist -- jsdom without the
 * shim, and any server-side render. Desktop is the safer default: it is the
 * layout every existing test and story was written against.
 */
export function isHandheld(): boolean {
  try {
    return window.matchMedia(HANDHELD_QUERY).matches;
  } catch {
    return false;
  }
}

/**
 * The same question, asked of an explicit size.
 *
 * Exported so the unit tests can pin the boundary without pretending to resize
 * a window, and so the zoom solver can reason about a viewport it has measured
 * rather than re-querying.
 */
export function isHandheldSize(width: number, height: number): boolean {
  return width <= HANDHELD_MAX_W || height <= HANDHELD_MAX_H;
}

/*
 * ...AND WHERE IT STOPS BEING A HANDHELD AND BECOMES A PHONE.
 *
 * A phone is a handheld too -- it keeps `data-handheld` and everything the Deck
 * layout already does for a small screen -- but the Deck's floors are written
 * for 1280x800. A 96px card, a 224px rail and a 132px info column are fine on
 * a Deck and leave an iPhone's battlefield 0px wide in portrait and 34px tall
 * in landscape. So the phone tier is ADDITIVE: `data-phone` on `<html>`, and
 * `styles/phone.css` relaxes the floors and restacks the table under it.
 *
 * THE NUMBERS. 600 wide catches every phone held upright (the widest common one
 * is 430) and no tablet. 500 tall catches every phone held sideways (the
 * tallest is 430) and no laptop window anybody plays in. As with the handheld
 * query, either dimension is enough on its own.
 */

export const PHONE_MAX_W = 600;
export const PHONE_MAX_H = 500;

/** The phone query, as `styles/phone.css` and `matchMedia` both see it. */
export const PHONE_QUERY = `(max-width: ${PHONE_MAX_W}px), (max-height: ${PHONE_MAX_H}px)`;

export function isPhone(): boolean {
  try {
    return window.matchMedia(PHONE_QUERY).matches;
  } catch {
    return false;
  }
}

export function isPhoneSize(width: number, height: number): boolean {
  return width <= PHONE_MAX_W || height <= PHONE_MAX_H;
}
