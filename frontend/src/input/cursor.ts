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
import { setGroup } from "./groups";
import { getInputMode, subscribeInputMode } from "./inputMode";
import { type Dir, unreachableStops } from "./nav";
import { padDiagnostics } from "./pad";
import { followRing, retargetRing, ringNudge, ringTargetFor } from "./ring";
import {
  candidatesIn,
  escapeGroup,
  navigate,
  stopElement,
  stopIdOf,
  stopRoot,
  stopsIn,
} from "./stops";

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
 * Bring a stop that is merely scrolled away back into view.
 *
 * `stops.ts:onScreen` deliberately lets the ring travel to a stop inside a
 * scrollable box that is currently past its edge -- a deck eleven rows down the
 * catalogue is somewhere you can go, unlike a card in a clipped lane. This is
 * the other half of that: having gone there, the box has to follow, or the ring
 * is drawn at a position nobody can see and the screen looks frozen.
 *
 * `el.focus({ preventScroll: true })` is what makes this necessary rather than
 * free. That flag is right on the board -- the scroll there is the fit solver's
 * business and a browser scroll fights it -- so the scroll is put back
 * deliberately, only for boxes that are genuinely scrollers, and never for the
 * board's own root.
 *
 * The minimum move, and only the first scroller: a stop already inside its box
 * does not move it at all, or the catalogue would jump a row every time the
 * ring stepped sideways. See `SCROLLS` for why this does the arithmetic itself
 * rather than calling `scrollIntoView`.
 */
function keepInView(el: HTMLElement): void {
  const box = el.getBoundingClientRect();
  if (box.width <= 0 && box.height <= 0) return;
  for (let a = el.parentElement; a; a = a.parentElement) {
    if (a.classList.contains("table")) return;
    const style = getComputedStyle(a);
    const scrollsY = SCROLLS.has(style.overflowY) && a.scrollHeight > a.clientHeight;
    const scrollsX = SCROLLS.has(style.overflowX) && a.scrollWidth > a.clientWidth;
    if (!scrollsY && !scrollsX) continue;
    const view = a.getBoundingClientRect();
    if (scrollsY) a.scrollTop += overshoot(box.top, box.bottom, view.top, view.bottom);
    if (scrollsX) a.scrollLeft += overshoot(box.left, box.right, view.left, view.right);
    return;
  }
}

/**
 * Only `auto` and `scroll`, and never `hidden`.
 *
 * `Element.scrollIntoView` was the obvious way to write `keepInView` and is the
 * wrong one: it scrolls EVERY scrollable ancestor up to the viewport, and an
 * `overflow: hidden` box is still programmatically scrollable. `.room` is
 * `overflow: hidden` -- it is a full-bleed stage that must never move -- so
 * opening the catalogue and putting the ring on a deck scrolled the whole hall
 * 121px up its own box and took the header off the top of the screen with it.
 * Nothing in the DOM looked wrong; the room had simply been scrolled.
 */
const SCROLLS = new Set(["auto", "scroll", "overlay"]);

/** How far to move a scroller so `[near, far]` sits inside `[low, high]`. */
function overshoot(near: number, far: number, low: number, high: number): number {
  if (near < low) return near - low;
  if (far > high) return far - high;
  return 0;
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
function stamp(el: HTMLElement | null, focus = true): void {
  const doc = el?.ownerDocument ?? document;
  for (const other of doc.querySelectorAll<HTMLElement>("[data-cursor]")) {
    if (other !== el) other.removeAttribute("data-cursor");
  }
  if (!el) return;
  el.setAttribute("data-cursor", "");
  keepInView(el);
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
   *
   * `focus` is how a caller says this stamp is not a move the player asked for
   * -- see `resolveCursor`, which runs after every commit and must not be able
   * to take a field away from somebody typing in it.
   */
  if (!focus) return;
  if (el.tabIndex < 0) return;
  el.focus({ preventScroll: true });
  if (doc.activeElement === el) return;
  /*
   * IT ASKED FOR FOCUS AND DID NOT GET IT, so the focus it left behind has to
   * go rather than stay pointing at the stop before this one.
   *
   * A DISABLED CONTROL IS A STOP ON PURPOSE -- `stops.ts` spends a paragraph on
   * why, and "walk onto a greyed-out action to read why it is greyed out" is
   * the argument. But `focus()` on one is a silent no-op, so the ring moved and
   * DOM focus stayed on whatever control it was on last.
   *
   * That is not a cosmetic mismatch, because `focusHolder` reads it straight
   * back: a focused element that is not the ring's is treated as focus the
   * player moved themselves, and followed. So the ring could not REST on a
   * disabled control standing next to an enabled one -- it arrived, and the
   * next `resolveCursor` (one per engine push, which during an opponent's turn
   * is several a second) saw the stale focus and pulled it back.
   *
   * The combat bar is exactly that shape. Attack/Block sits beside the "all"
   * mark and is disabled until something is staged, which is precisely its
   * state at the instant the decision opens -- so stepping right onto it held
   * for about forty milliseconds and snapped back to the mark, again and again.
   * From the player's side the button that declares the attack could not be
   * reached at all.
   *
   * NARROWED TO STOPS THAT ASKED. A card is a div with `tabIndex` -1: it never
   * asks for focus, `focusHolder` already ignores stale focus underneath it for
   * that reason, and blurring there would take focus off a control for no
   * reason at all. The returns above are what keep that case untouched.
   *
   * Asked as "did focus actually land" rather than by reading `disabled`,
   * because there is more than one way an element declines it and the answer to
   * all of them is the same.
   */
  const active = doc.activeElement as HTMLElement | null;
  if (active && active !== doc.body && active !== doc.documentElement) active.blur();
}

/**
 * Whether somebody else is holding real focus.
 *
 * `<body>` is not somebody: it is what the browser falls back to when the
 * focused element is removed, which is the case `resolveCursor` exists to
 * repair.
 */
function heldElsewhere(el: HTMLElement): boolean {
  const doc = el.ownerDocument;
  const active = doc.activeElement;
  if (!active || active === el) return false;
  return active !== doc.body && active !== doc.documentElement;
}

/**
 * THE RING FOLLOWS FOCUS THE PLAYER MOVED THEMSELVES.
 *
 * Off the board every stop is a native control (see `stopsIn`), so the cursor
 * and DOM focus are two names for one thing and they have to agree. They did
 * not: clicking into the seed field put focus there and left the cursor on the
 * first control in the header -- and because `resolveCursor` runs after *every*
 * commit, the next keystroke re-stamped that control, `focus()`d it, and threw
 * the caret out of the field. One character typed, then nothing: the pod's
 * `Copy` button wearing the ring while you were typing a seed.
 *
 * Returns the index of the focused stop, or -1 when focus says nothing useful.
 * It says nothing when the stop the ring is on cannot take focus at all, which
 * is the board's whole surface -- cards are divs, so there the focused element
 * is merely whatever control was pressed last, and following it would drag the
 * ring off the card the player just walked it onto.
 */
function focusHolder(all: HTMLElement[], current: HTMLElement): number {
  if (current.tabIndex < 0) return -1;
  const active = current.ownerDocument.activeElement as HTMLElement | null;
  if (!active || active === current) return -1;
  return all.indexOf(active);
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
/**
 * Where the ring was standing before each overlay opened, innermost last.
 *
 * THE BUG THIS EXISTS FOR IS THE ONE THAT ENDS A CONTROLLER SESSION.
 *
 * Press A on a deck in the catalogue: the catalogue closes, the cursor names a
 * tile that no longer exists, and the fallback below -- "the first stop of
 * whatever is on top" -- put the ring on the first control in the pod's header,
 * which is the `Copy` button. Every A press that dismissed anything threw the
 * player back to the top-left of the screen, so choosing a deck and then
 * locking in was two full walks of the lobby with a wrong turn in the middle.
 * The player's word for it was that the pad "doesn't work".
 *
 * A return address is the honest fix, because closing an overlay is not a
 * navigation: the ring was somewhere before it opened, that place is still
 * there, and going back to it is what the screen behind the overlay means. It
 * is a stack rather than a single slot because the catalogue can open a dossier
 * over itself, and backing out of that must land on the tile rather than at the
 * catalogue's own front.
 *
 * Keyed by the ROOT ELEMENT rather than by a name, so nothing has to be told
 * about a new dialog for this to cover it -- `stopRoot` already answers "which
 * surface owns the ring", and a change in that answer is exactly the event this
 * has to see.
 */
const returns: { root: HTMLElement; stop: string | null }[] = [];
let lastRoot: HTMLElement | null = null;

/**
 * Notice a change of surface, and say what the ring was on last time we were
 * standing on this one.
 *
 * Returns null in the ordinary case -- same surface as the last resolve, or a
 * surface we have never been on. Only backing OUT of an overlay produces an
 * address, which is the only case where "put the ring back" is what a player
 * means.
 */
/**
 * Called from `setCursor` too, and that is not belt-and-braces.
 *
 * An overlay that puts the ring somewhere sensible on the way in -- which the
 * deck catalogue does, landing on a deck rather than on its own ✕ -- calls
 * `setCursor` from a layout effect, BEFORE the `MutationObserver` gets round to
 * re-resolving. So by the time `resolveCursor` noticed the surface had changed,
 * the cursor it filed as the return address was already the tile inside the new
 * surface. Closing the catalogue then had an address that no longer existed,
 * fell through to nearest-to-where-you-were, and measured from the middle of
 * the grid to the pod behind it: the header's first button, every time.
 *
 * Noting the change from both entry points is what makes the address the stop
 * the player was ACTUALLY standing on when the overlay opened.
 */
function noteRoot(): void {
  trackRoot(stopRoot());
}

/**
 * What happened to the surface the ring is on, between one resolve and the next.
 *
 *   same    nothing moved; a stop may still have been rebuilt under the ring
 *   enter   a surface we have not been on before is now on top
 *   return  we have backed out to one we left, and `stop` is where we left it
 */
type RootMove = { kind: "same" | "enter" } | { kind: "return"; stop: string | null };

function trackRoot(root: HTMLElement): RootMove {
  if (root === lastRoot) return { kind: "same" };
  const known = returns.findIndex((entry) => entry.root === root);
  if (known >= 0) {
    const stop = returns[known].stop;
    // Everything deeper than the surface we came back to is gone for good; an
    // overlay that reopens gets a fresh address rather than a stale one.
    returns.length = known;
    lastRoot = root;
    return { kind: "return", stop };
  }
  if (lastRoot?.isConnected) returns.push({ root: lastRoot, stop: cursor });
  lastRoot = root;
  return { kind: "enter" };
}

/**
 * The stop nearest to where the ring was, for when its own stop is gone and
 * there is no overlay to back out of.
 *
 * The case is a control that rebuilt itself into something else: pressing
 * "Add a CPU" replaces that whole chair with a CPU's, so the button the ring
 * was on ceases to exist while the screen around it barely moves. Jumping to
 * the first stop on the surface there is just as wrong as it was for the
 * overlay, and there is no address to return to -- but there IS a position, and
 * the thing that took the old control's place is almost always the thing under
 * it. Nearest-to-where-you-were is the answer a player never has to think
 * about.
 *
 * Distances are between box centres and measured in the same sweep `navigate`
 * already makes on every press, so this costs nothing that was not already
 * being spent.
 */
function nearestTo(all: HTMLElement[], from: DOMRect): number {
  const fx = from.left + from.width / 2;
  const fy = from.top + from.height / 2;
  let best = -1;
  let bestD = Number.POSITIVE_INFINITY;
  for (let i = 0; i < all.length; i += 1) {
    const rect = all[i].getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    const dx = rect.left + rect.width / 2 - fx;
    const dy = rect.top + rect.height / 2 - fy;
    const d = dx * dx + dy * dy;
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

/** The last box the ring was aimed at, for `nearestTo`. */
let lastAim: DOMRect | null = null;

export function resolveCursor(): void {
  const root = stopRoot();
  const move = trackRoot(root);
  const all = stopsIn(root);
  let index = cursor === null ? -1 : all.findIndex((node, i) => stopIdOf(node, i) === cursor);
  // Backing out of an overlay: the ring goes to the control that opened it.
  if (index < 0 && move.kind === "return" && move.stop !== null) {
    const back = move.stop;
    index = all.findIndex((node, i) => stopIdOf(node, i) === back);
  }
  /*
   * A stop that rebuilt itself into something else: the ring stays where it was
   * standing rather than walking to the front of the screen.
   *
   * ONLY WHEN THE SURFACE ITSELF DID NOT CHANGE, and that clause is the whole
   * difference between this and a bug. A dialog opening over the board is not a
   * stop being replaced -- it is a new screen -- and measuring from where the
   * ring stood BEHIND it is measuring across two things that were never on
   * screen together. The mulligan prompt found it: the ring had been on a hand
   * card at the bottom of the board, so the nearest option in the new panel was
   * whichever one happened to sit lowest, and the prompt opened on its second
   * option for reasons nothing on screen could explain.
   */
  if (index < 0 && move.kind === "same" && lastAim && all.length > 0) {
    index = nearestTo(all, lastAim);
  }
  // And only then the first stop of whatever surface is on top -- deliberately
  // the topmost surface's first and not the document's, or opening a dialog
  // would leave the ring on the board behind it.
  if (index < 0) index = 0;
  let el: HTMLElement | null = all[index] ?? null;
  if (!el) {
    if (cursor !== null) {
      cursor = null;
      announce();
    }
    clearStamp();
    return;
  }
  const taken = focusHolder(all, el);
  if (taken >= 0) {
    index = taken;
    el = all[index];
  }
  // `stopIdOf`, not `dataset.stop`: outside the board a stop is a native
  // focusable with no declared id, and reading the attribute directly gave
  // every lobby control an id of `undefined` -- so the ring mounted, resolved
  // to nothing, and the entire lobby was unreachable by controller.
  const next = stopIdOf(el, index);
  const moved = next !== cursor;
  cursor = next;
  // A commit is not a request to move focus. The exception is a cursor that
  // genuinely moved -- a dialog opening over the board resolves the ring into
  // it, and focus has to come along or the trap is only a picture of one.
  stamp(el, moved || !heldElsewhere(el));
  aimRing(el);
  if (moved) {
    announce();
    hoverFor(next);
  }
}

/**
 * Point the ring at an element, and tell it how to keep re-reading that element.
 *
 * The closure is the second half and it is the one that matters: `ringTargetFor`
 * is a snapshot, and a stop can change shape without the cursor going anywhere.
 * See `measure` in `input/ring.ts` for the case that found it.
 */
function aimRing(el: HTMLElement): void {
  const target = ringTargetFor(el);
  // Kept for `nearestTo`, which needs to know where the ring WAS after the
  // element it was on has already left the document.
  lastAim = el.getBoundingClientRect();
  retargetRing(target.rect, context, target.angle, () => ringTargetFor(el));
}

/**
 * The thing the ring is on has started moving; go with it.
 *
 * Distinct from `restampCursor`, and deliberately much cheaper: nothing about
 * *which* stop the cursor is on has changed, so there is no reason to re-derive
 * it or to sweep `stopsIn`. This only wakes the spring, which then follows the
 * element frame by frame until it comes to rest.
 *
 * `HandFan` calls it, because raising a card is the one animation that reshapes
 * a stop the ring may already be sitting on.
 */
export function refollowCursor(): void {
  if (cursor === null) return;
  const el = stopElement(cursor);
  if (!el) return;
  aimRing(el);
  followRing();
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
  if (next) {
    setCursor(next);
    return true;
  }
  /*
   * Nowhere to go inside the region means out of the region -- see
   * `escapeGroup`, which refuses for a modal so this cannot walk out from under
   * a dialog. Without it a controller with no shoulder buttons, which is what a
   * Steam Deck in gaming mode is, was locked in one region for the whole game.
   */
  const out = escapeGroup(cursor, dir);
  if (out) {
    /*
     * THE REGION HAS TO BE RELEASED BEFORE THE CURSOR MOVES, and leaving that
     * out made the whole escape a no-op that looked like it worked.
     *
     * `setCursor` resolves its target through `stopElement`, which defaults to
     * `activeRoot()` -- and `activeRoot()` is still the region we are trying to
     * leave. So the stop `escapeGroup` had just found, outside that region, was
     * not findable from inside it: `setCursor` returned false and the ring sat
     * exactly where it was. Every unit test passed, because they call
     * `escapeGroup` directly and it was returning the right answer all along.
     *
     * Clearing the group first widens `activeRoot` back to the board for the one
     * call that needs it. `Table`'s reconciler then reads the new cursor and
     * sets the region it actually landed in, which is why nothing here has to
     * work out what that region is.
     */
    setGroup(null);
    if (setCursor(out)) return true;
  }
  // A wall you can see. The nudge, the deny voice and the rumble are three
  // channels for one fact, because a handheld is routinely played muted and
  // `vibrationActuator` does not exist in every browser.
  ringNudge(dir);
  return false;
}

/** Put the ring on a named stop, if it is currently reachable. */
export function setCursor(id: string | null): boolean {
  noteRoot();
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
  aimRing(el);
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
 * Which card the ring, sitting on this stop, is reading.
 *
 * A `card:` stop IS a card and answers for itself. Anything else has to say so,
 * and `data-preview-oid` is how: an action row is a decision *about* a card that
 * is somewhere else on the board, and the panel already writes that fact for the
 * pointer (`ActionPanel`'s `previewing`).
 *
 * Reading the attribute rather than trusting the row's own `onFocus` is what
 * makes the two agree. `hoverFor` runs *after* `stamp()` has moved DOM focus, so
 * a null here does not leave the row's write standing -- it overwrites it, and
 * the rail went blank the instant the ring landed on the row that had just
 * filled it. One source for both inputs, or they drift.
 */
function previewOidFor(stop: string): number | null {
  // `Number(null)` is 0 and `Number.isFinite(0)` is true, so the missing
  // attribute has to be caught before it becomes a hover on the zeroth object.
  const declared = stop.startsWith("card:")
    ? stop.slice(5)
    : stopElement(stop)?.getAttribute("data-preview-oid");
  if (!declared) return null;
  const oid = Number(declared);
  return Number.isFinite(oid) ? oid : null;
}

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
  const oid = stop === null ? null : previewOidFor(stop);
  const store = useUiStore.getState();
  const apply = () => {
    store.hover(oid);
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
  lastAim = null;
  lastRoot = null;
  returns.length = 0;
  listeners.clear();
  if (typeof document !== "undefined") {
    for (const el of document.querySelectorAll<HTMLElement>("[data-cursor]")) {
      el.removeAttribute("data-cursor");
    }
    document.documentElement.removeAttribute("data-sweeping");
  }
}
