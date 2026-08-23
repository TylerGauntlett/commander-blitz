/**
 * The cursor: one string, and one attribute on one element.
 *
 * THE RULE THIS FILE EXISTS TO ENFORCE, and it cost the design round three
 * times its frame rate to find:
 *
 * > The cursor wants to live as an attribute on ONE element, not as state
 * > thirty components read.
 *
 * A cursor in zustand that every `Card` subscribes to re-renders all thirty
 * cards on every step of a sweep. Under a 4x CPU throttle -- a fair proxy for
 * the Deck's APU -- that measured 28.2ms per frame and 18.5fps while a
 * direction was held, against 59.7fps for moving one attribute. The React
 * version of the mistake looks completely different from the vanilla one and
 * arrives at the identical number.
 *
 * So: nothing here is React state. `Card`, `Lane`, `PlayerOrb` and the rest
 * render `data-stop` as a static prop derived from their own props, and never
 * re-render because the ring moved. This module writes `data-cursor` on one
 * node imperatively and tells the spring in `ring.ts` where it went.
 *
 * The one thing that *is* allowed to re-render is the read rail, because
 * reading the card under the ring is the whole point of the ring. That write is
 * debounced -- see `settleHover` -- so a twelve-step sweep costs two rail
 * rebuilds rather than twelve.
 */

import { useUiStore } from "../state/uiStore";
import { getInputMode, subscribeInputMode } from "./inputMode";
import { type Dir, unreachableStops } from "./nav";
import { padDiagnostics } from "./pad";
import { retargetRing, ringNudge } from "./ring";
import { candidatesIn, navigate, stopElement, stopIdOf, stopRoot, stopsIn } from "./stops";

/** The stop the ring is on. Not React state; see the header. */
let cursor: string | null = null;

/**
 * The screen and overlay the cursor is on, for the spring's teleport rule.
 *
 * A spring across a screen change is a spring across nothing: flying the ring
 * from a lobby seat to a board card is 600px of travel between two things that
 * were never on screen together, and it reads as a glitch. `Table` and the
 * lobby screens set this; a change means snap rather than fly.
 */
let context = "";

type Listener = (stop: string | null) => void;
const listeners = new Set<Listener>();

/** The current stop id. */
export function getCursor(): string | null {
  return cursor;
}

/**
 * Subscribe to cursor moves.
 *
 * Deliberately NOT a React hook, and deliberately not exported as one for
 * general use. Two consumers subscribe -- the hint bar and the read rail -- and
 * both are single components at the edge of the tree. A `useCursor()` available
 * to any component is exactly how the 18fps comes back.
 */
export function subscribeCursor(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function announce(): void {
  for (const listener of listeners) listener(cursor);
}

export function setCursorContext(next: string): void {
  context = next;
}

/**
 * Put `data-cursor` on exactly one element and take it off every other.
 *
 * The query is document-wide rather than scoped to the trapped root, because
 * the node that must lose the attribute is frequently *outside* the root -- that
 * is what happens the moment a modal opens over a board that had the ring.
 * `e2e/handheldAssert.ts` fails the run on more than one cursor, and this is
 * the function that makes that assertion true.
 */
function stamp(el: HTMLElement | null): void {
  const doc = el?.ownerDocument ?? document;
  for (const other of doc.querySelectorAll<HTMLElement>("[data-cursor]")) {
    if (other !== el) other.removeAttribute("data-cursor");
  }
  if (!el) return;
  el.setAttribute("data-cursor", "");
  /*
   * Move real DOM focus too, when the element can take it.
   *
   * Not for the ring -- the ring is `[data-cursor]` and the attribute alone
   * draws it -- but so a screen reader follows the same object the sighted
   * player is on, and so a keystroke that only a focused control handles
   * reaches it. `preventScroll` because the scroll is the lane's business and
   * a browser scroll would fight the fit solver.
   *
   * This is precisely why `:focus:not([data-cursor])` in `handheld.css` has to
   * carry that `:not()`: we are deliberately creating a focused element that
   * must not also draw the native outline.
   */
  if (el.tabIndex >= 0) el.focus({ preventScroll: true });
}

/** Remove the cursor from wherever it is, and stand the ring down. */
function clearStamp(): void {
  for (const other of document.querySelectorAll<HTMLElement>("[data-cursor]")) {
    other.removeAttribute("data-cursor");
  }
  retargetRing(null, context);
}

/**
 * Re-derive the cursor from state after the DOM has changed.
 *
 * Called from a layout effect with NO dependency array, so it runs after every
 * commit of the component it is mounted in -- and `Table` re-renders on every
 * engine push. This is the fix for the worst bug the design round found: walk
 * the ring onto the commit slab, the slab is rebuilt, the ring goes out, and it
 * can never come back off -- because navigation starts from `[data-cursor]` and
 * there no longer is one.
 *
 * The mockup needed an `again` flag here to rebuild once more after resolving.
 * React does not: by the time a layout effect runs, the final markup already
 * exists. What replaces it is that everything reading the cursor to *build*
 * markup reads it on the next tick, through `subscribeCursor`.
 */
export function resolveCursor(): void {
  const root = stopRoot();
  let el = cursor ? stopElement(cursor, root) : null;
  let index = 0;
  if (!el) {
    // Fall back to the first stop of whatever surface is on top. Deliberately
    // the topmost surface's first stop and not the document's, or opening a
    // dialog would leave the ring on the board behind it.
    el = stopsIn(root)[0] ?? null;
  } else {
    index = stopsIn(root).indexOf(el);
  }
  if (!el) {
    if (cursor !== null) {
      cursor = null;
      announce();
    }
    clearStamp();
    return;
  }
  // `stopIdOf`, not `dataset.stop`: outside the board a stop is a native
  // focusable with no declared id, and reading the attribute directly gave
  // every lobby control an id of `undefined` -- so the ring mounted, resolved
  // to nothing, and the entire lobby was unreachable by controller.
  const next = stopIdOf(el, Math.max(0, index));
  const moved = next !== cursor;
  cursor = next;
  stamp(el);
  retargetRing(el.getBoundingClientRect(), context);
  if (moved) {
    announce();
    hoverFor(next);
  }
}

/**
 * Re-stamp after a partial rebuild that React did not commit through `Table`.
 *
 * `AnimatePresence` exits and framer `layoutId` node swaps both replace DOM
 * outside the commit that a layout effect observes, so the element wearing
 * `data-cursor` can simply cease to exist between renders. A
 * microtask-coalesced `MutationObserver` calls this; `FocusRing` owns it.
 */
export function restampCursor(): void {
  resolveCursor();
}

/** Move the ring, or draw the wall it could not cross. */
export function moveCursor(dir: Dir): boolean {
  const next = navigate(cursor, dir);
  if (!next) {
    // A wall you can see. The nudge, the deny voice and the rumble are three
    // channels for one fact, because a handheld is routinely played muted and
    // `vibrationActuator` does not exist in every browser.
    ringNudge(dir);
    return false;
  }
  setCursor(next);
  return true;
}

/** Put the ring on a named stop, if it is currently reachable. */
export function setCursor(id: string | null): boolean {
  if (id === null) {
    cursor = null;
    clearStamp();
    announce();
    return true;
  }
  const el = stopElement(id);
  if (!el) return false;
  cursor = id;
  stamp(el);
  retargetRing(el.getBoundingClientRect(), context);
  announce();
  hoverFor(id);
  return true;
}

// ------------------------------------------------------------- the read rail

/**
 * How long a step has to stand still before the rail rebuilds for it.
 *
 * A sweep is a sequence of steps under ~110ms apart, and during one the player
 * is not reading anything -- they are travelling. Rebuilding the preview for
 * every card passed costs a React render *and* re-derives the mana-spend
 * forecast, twelve times, to show twelve cards nobody looked at.
 *
 * This is worth more here than it was in the prototype, which had no React and
 * no solver behind its rail. `.preview--sweeping` goes on immediately, so the
 * delay reads as the rail deferring rather than as the rail lagging.
 */
export const RAIL_SETTLE = 110;

let settleTimer: ReturnType<typeof setTimeout> | null = null;
let lastStep = 0;

/**
 * Drive `hoveredOid` from the cursor.
 *
 * This one line is what hands the pad the three hover-only surfaces the client
 * had no other route to: the card preview rail, the `CardStack` fan, and the
 * unplayable-card hint. All three already key off `hoveredOid`, so none of them
 * needed a second code path -- which is also why they cannot drift from what
 * the mouse does.
 */
function hoverFor(stop: string | null): void {
  /*
   * ONLY WHEN THE RING IS THE THING BEING USED.
   *
   * The cursor exists in every input mode -- it resolves on every commit so it
   * is ready the moment somebody picks up a controller -- but a mouse player
   * has no ring on screen, and driving `hoveredOid` from an invisible cursor
   * means the preview rail fills with a card they never pointed at and the
   * mana row forecasts a spend for a spell they never considered.
   *
   * That is precisely the kind of change to the mouse experience this whole
   * feature is supposed not to make, and it is invisible until something
   * measures it -- `e2e/cycle3.spec.ts` caught it as a mana row reporting a
   * spend of 2 with nothing hovered.
   */
  if (getInputMode() === "mouse") return;
  const oid = stop?.startsWith("card:") ? Number(stop.slice(5)) : null;
  const store = useUiStore.getState();
  const apply = () => {
    store.hover(Number.isFinite(oid) ? oid : null);
    setSweeping(false);
  };

  const now = performance.now();
  const sweeping = now - lastStep < RAIL_SETTLE;
  lastStep = now;

  if (settleTimer) clearTimeout(settleTimer);
  if (!sweeping) {
    apply();
    return;
  }
  setSweeping(true);
  settleTimer = setTimeout(apply, RAIL_SETTLE);
}

/**
 * Hand the rail back when the pointer takes over.
 *
 * `hoverFor` refuses to write `hoveredOid` in mouse mode, which is the right
 * rule and is not enough on its own: the write that has to be undone happened
 * *before* the mode changed. A player walks the ring onto a hand card, the card
 * lifts and the preview fills, and then they touch the mouse -- and nothing
 * clears it, because no `mouseleave` can fire for a card the pointer was never
 * over. The result is a card pinned raised for the rest of the game and a
 * preview rail reading something nobody is pointing at.
 *
 * The pending `settleTimer` has to go with it, and that is not belt-and-braces:
 * a sweep's deferred `apply()` is up to `RAIL_SETTLE` in the future, so without
 * this the rail re-lights ~110ms *after* the mouse has already taken over.
 *
 * Only the mouse direction is handled. Going the other way -- mouse to ring --
 * needs nothing, because the next `hoverFor` writes the cursor's own card and
 * the mouse's leave handler still fires normally.
 */
subscribeInputMode(() => {
  if (getInputMode() !== "mouse") return;
  if (settleTimer) {
    clearTimeout(settleTimer);
    settleTimer = null;
  }
  setSweeping(false);
  useUiStore.getState().hover(null);
});

/**
 * Mark the rail as travelling.
 *
 * An attribute on the root rather than a store flag, for the same reason the
 * cursor is: this fires on every step of every sweep, and a store write here
 * would re-render the board at exactly the moment the deferral is trying to
 * stop it from re-rendering.
 */
function setSweeping(on: boolean): void {
  if (typeof document === "undefined") return;
  document.documentElement.toggleAttribute("data-sweeping", on);
}

/**
 * Diagnostics, in dev and test builds only.
 *
 * `e2e/handheldAssert.ts` and the playtest driver both need to ask the app what
 * the ring can see -- and asking it by re-implementing the scoring in the page
 * would be asking a different question, which is how a gate ends up passing
 * against a real defect. This publishes the real answers.
 */
if (import.meta.env?.DEV) {
  (window as unknown as Record<string, unknown>).__AUTOMTG_RING = {
    cursor: () => cursor,
    stops: () => candidatesIn().map((c) => c.id),
    unreachable: () => unreachableStops(candidatesIn()),
    /*
     * The pad, published beside the ring because the question a human asks is
     * always about both: "the controller does nothing" is either a loop that is
     * not running, a browser that cannot see the pad, or a ring suppressed
     * because the mode is still `mouse`. One call, three answers.
     */
    pad: () => ({ ...padDiagnostics(), mode: getInputMode() }),
    /* What the read rail is pinned to. The stuck-hover class of bug is only
       ever visible as a mismatch between this and where the pointer is. */
    hovered: () => useUiStore.getState().hoveredOid,
  };
}

/** Test seam: the module is a singleton and stories mount repeatedly. */
export function resetCursor(): void {
  if (settleTimer) clearTimeout(settleTimer);
  settleTimer = null;
  lastStep = 0;
  cursor = null;
  context = "";
  listeners.clear();
  if (typeof document !== "undefined") {
    for (const el of document.querySelectorAll<HTMLElement>("[data-cursor]")) {
      el.removeAttribute("data-cursor");
    }
    document.documentElement.removeAttribute("data-sweeping");
  }
}
