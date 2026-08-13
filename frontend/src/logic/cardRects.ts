/**
 * Where each card was, the last time anybody looked.
 *
 * The effects layer resolves its anchors from the live DOM at the moment a beat
 * plays (`FxLayer.anchorPoint`), which works for everything that is still on the
 * board and for nothing that has left it. A card being destroyed is precisely a
 * card that is no longer rendered: `useGame` commits the new state and *then*
 * pushes the beats, so by the time the death beat plays its `[data-oid]` element
 * is gone and the lookup returns null. That is why a dying permanent used to
 * animate nothing at all.
 *
 * So `Card` posts its box here on the way out, and the ghost is drawn from the
 * last position the card actually occupied.
 *
 * Rects are in **viewport** coordinates, the same as `getBoundingClientRect`.
 * Callers subtract their own container's origin, exactly as `anchorPoint` and
 * `CombatArrows.centreOf` already do.
 *
 * Pure: this module never reads the DOM. The caller measures and hands the
 * result over, which is what keeps it testable without a layout engine.
 */

export interface CardRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface Remembered {
  rect: CardRect;
  at: number;
}

/**
 * How many cards to remember.
 *
 * A Commander game can churn hundreds of objects, and every one of them would
 * otherwise stay here for the length of the session. The map is
 * insertion-ordered, so the oldest entry is the first key.
 */
const CAP = 200;

/**
 * How long a remembered position stays trustworthy.
 *
 * Long enough to cover a narration queue draining a whole AI turn, short enough
 * that a card which left the board a minute ago cannot resurface at coordinates
 * that no longer mean anything -- the window may have been resized or the zoom
 * changed since.
 */
const MAX_AGE_MS = 30_000;

const seen = new Map<number, Remembered>();

/** The clock, injectable so the age test does not have to sleep. */
let now = () => Date.now();

/**
 * Record where a card is.
 *
 * Zero-sized rects are dropped rather than stored. jsdom returns all-zero boxes
 * for everything, so without this guard every unit test that mounts a board
 * would poison the map with origin-anchored positions and the ghost would fly
 * out of the top-left corner. `CombatArrows.centreOf` rejects them for the same
 * reason.
 */
export function remember(oid: number, rect: CardRect): void {
  if (rect.width <= 0 || rect.height <= 0) return;
  // Delete first so a re-remembered card moves to the end of the insertion
  // order and is not the next one evicted.
  seen.delete(oid);
  seen.set(oid, {
    rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    at: now(),
  });
  if (seen.size > CAP) {
    const oldest = seen.keys().next();
    if (!oldest.done) seen.delete(oldest.value);
  }
}

/** Where a card was, or null if it was never seen or was seen too long ago. */
export function recall(oid: number): CardRect | null {
  const found = seen.get(oid);
  if (!found) return null;
  if (now() - found.at > MAX_AGE_MS) {
    seen.delete(oid);
    return null;
  }
  return found.rect;
}

/** Drop everything. Called when a table unmounts, and between tests. */
export function reset(): void {
  seen.clear();
}

/** Test seam for the age check. Pass nothing to restore the real clock. */
export function setClock(clock?: () => number): void {
  now = clock ?? (() => Date.now());
}
