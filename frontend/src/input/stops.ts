/**
 * Where the ring is allowed to be, and which of those places is on top.
 *
 * A stop is any element carrying `data-stop`. The value is a **string
 * namespace, never an index**, so it survives a re-render, a reorder, a card
 * moving zone and a whole new game -- `card:14` is the same stop whether that
 * permanent is drawn first in its lane or last. An index would put the ring on
 * a different card every time the board changed under it.
 *
 * The namespaces:
 *
 *   card:<oid>            a permanent, a hand card, a stack item, a prompt option
 *   orb:<pid>             a seat
 *   act:<actionId>        anything carrying `data-action-id`
 *   tool:<name>           mute, full control, manual mana, undo, quit
 *   pile:<pid>:<zone>     a zone chip on the orb
 *   lane:<pid>:<lane>     an empty lane -- a destination with nothing in it yet
 *   commit                the commit slab
 *
 * ONE RULE TIES THIS TO THE ACTION PANEL'S INVARIANT: every element carrying
 * `data-action-id` also carries `data-stop="act:<id>"`. That is one derived
 * attribute on a node that already exists, so "every legal action is a button,
 * exactly once in the document" is untouched -- and `tests/stops.test.tsx` can
 * assert the two sets are in bijection.
 */

import { type GroupId, getGroup, groupRoot } from "./groups";
import { type Candidate, type Dir, nearestStop, pickStop } from "./nav";

/**
 * The two attributes an action control carries, together.
 *
 * Spread this rather than writing `data-action-id` by hand. The panel's
 * invariant is that every legal action is a button carrying that attribute
 * exactly once in the document; the ring's requirement is that every such
 * button is reachable. Emitting both from one call makes the two sets equal
 * **by construction** instead of by eleven separate remembering-tos, and
 * `tests/stops.test.tsx` fails the build if a bare `data-action-id` reappears.
 *
 * Note this adds no node and no id -- it is one extra attribute on a button
 * that already existed, so nothing about the invariant changes.
 */
export function actionAttrs(id: string): { "data-action-id": string; "data-stop": string } {
  return { "data-action-id": id, "data-stop": `act:${id}` };
}

/** Stop ids for the surfaces that are not actions. */
export const stopId = {
  card: (oid: number) => `card:${oid}`,
  orb: (pid: number) => `orb:${pid}`,
  tool: (name: string) => `tool:${name}`,
  pile: (pid: number, zone: string) => `pile:${pid}:${zone}`,
  lane: (pid: number, lane: string) => `lane:${pid}:${lane}`,
  commit: "commit",
} as const;

/**
 * THE FOCUS TRAP, AND WHY IT IS ONE FUNCTION.
 *
 * With an overlay open, every stop on the board behind it is still in the
 * document. A resolver that took the first `[data-stop]` in document order
 * opened the game-over screen with the ring sitting on an opponent's seat,
 * because the board comes first in the markup. On a mouse you would never
 * notice. On a pad it means the ring walks out of a modal and presses things
 * underneath it.
 *
 * This client has exactly that hole and for exactly that reason: five dialogs
 * with `aria-modal="true"`, and a backdrop that blocks only CLICKS. So this is
 * the one place to fix it -- whatever is on top owns the ring, and `nav`, the
 * pointer, the resolver and the CI gate all ask this same question.
 *
 * `:not([data-closing])` is the half the mockup could not discover, because it
 * had no `AnimatePresence`. Every dialog here animates out, so an *exiting*
 * dialog is still in the DOM for its exit duration -- and without the guard the
 * ring stays trapped in a panel that is fading away, making `B` look broken for
 * about 220ms. Dialogs render the attribute only while genuinely open.
 */
export function stopRoot(doc: Document = document): HTMLElement {
  const app =
    doc.querySelector<HTMLElement>(".table") ??
    doc.querySelector<HTMLElement>(".screen") ??
    doc.body;
  const wheel = app.querySelector<HTMLElement>(".wheelwrap");
  if (wheel) return wheel;
  /*
   * THE LAST MODAL, NOT THE FIRST, and one overlay opening over another is the
   * whole reason.
   *
   * `querySelector` returns document order, which for a single dialog over a
   * board is also the top of the stack -- so this read correctly right up until
   * the deck catalogue got a dossier openable from inside it. Both are children
   * of the pod lobby and the catalogue is written first, so the ring stayed
   * trapped in the catalogue *behind* the dossier: A pressed a deck tile nobody
   * could see, and B closed the wrong thing.
   *
   * Document order is the stacking order here because every overlay in this
   * client is rendered by the surface it opens over, after it. That is a real
   * invariant rather than a coincidence -- a portal would break it -- and it is
   * why this is a `.pop()` rather than a z-index sort nothing could keep true.
   */
  const modals = app.querySelectorAll<HTMLElement>("[data-modal-root]:not([data-closing])");
  return modals[modals.length - 1] ?? app;
}

/**
 * The box the ring may move inside, right now.
 *
 * THE MODAL TRAP ALWAYS WINS. If `stopRoot` returned anything but the board,
 * something is on top and owns the ring outright -- a group trap under it would
 * let a direction press reach the board behind an open prompt.
 *
 * THE GROUP TRAP IS THE SECOND ONE, and it exists because directional
 * navigation crosses a 96px seat strip, three lanes, a fanned hand and a 243px
 * rail one card at a time. `docs/handheld-playtest.md` Loop 1 records walking
 * the board as "a bad way to ask can you reach everything": reachable and
 * reachable-in-under-a-second are different properties and only the second is
 * playable. `L1`/`R1` step between regions; inside one, a thumb-flick cannot
 * throw the ring across the screen. See `input/groups.ts`.
 *
 * NO GROUP MEANS NO TRAP. Before the player has jumped anywhere, the ring is
 * free of the whole board, which is exactly how it behaved before this existed.
 *
 * SCOPED TO THE RING'S OWN INPUT MODES. A mouse player has no ring at all, and
 * a desktop keyboard user expects Tab-like freedom; trapping either inside a
 * region is a behaviour regression nobody asked for. `data-input` is already on
 * `<html>`, and reading it here is how a module function with no props can ask.
 *
 * Lives in this file rather than in `groups.ts` so the dependency runs one way:
 * the trap knows about regions, regions know nothing about the trap.
 */
export function activeRoot(doc: Document = document): HTMLElement {
  const modal = stopRoot(doc);
  const board = doc.querySelector<HTMLElement>(".table");
  if (!board || modal !== board) return modal;
  if (doc.documentElement.getAttribute("data-input") === "mouse") return modal;
  const group: GroupId | null = getGroup();
  if (group === null) return modal;
  return groupRoot(group, doc) ?? modal;
}

/**
 * What counts as focusable when nothing has declared itself a stop.
 *
 * `[tabindex="-1"]` is excluded, because that is an element saying out loud
 * that it is not a stop.
 *
 * A DISABLED CONTROL IS NOT. It used to be, on the reasoning that "a control
 * the player cannot press is not somewhere the ring should be able to rest",
 * and that reasoning is wrong twice over.
 *
 * It is wrong about the board, which already disagrees: every action button
 * carries a declared `data-stop`, disabled ones included, deliberately -- "a
 * decision always HAS a surface" is the panel's stated invariant, and walking
 * onto a greyed-out action to read why it is greyed out is how a player finds
 * out. The lobby was the only surface where that was not true.
 *
 * And it is wrong about what happens when a control becomes disabled UNDER the
 * ring. Every button in the pod goes `disabled` for the round-trip of any
 * mutation, so pressing "Add a CPU" deleted every stop on the screen except the
 * three in the header for about 200ms -- the ring had nowhere near to fall back
 * to, landed on the first header button, and stayed there when the pod came
 * back. From the player's side, adding a CPU threw the ring to the top-left
 * corner. Nothing was broken at either end of that; the stop list simply
 * emptied out for a fifth of a second.
 */
const FOCUSABLE = 'button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * Every stop inside `root`, in document order.
 *
 * TWO KINDS OF SURFACE, AND THE RULE IS DIFFERENT FOR EACH.
 *
 * The board declares its stops explicitly, because the things you point at
 * there are *cards* -- divs with a `role`, not controls -- and because which of
 * them is a target is a question only the game can answer. `data-stop` is how
 * it says so.
 *
 * Everywhere else -- the front door, the pod lobby, the deck catalogue, the
 * dossier -- every interactive thing already IS a native control. There, a
 * focusable element is a stop, full stop. That is not a shortcut: it means a
 * button added to the lobby next year is reachable by controller without
 * anybody remembering this file exists, which is the opposite of the failure
 * this whole layer is prone to.
 *
 * A surface that declares even one explicit stop is taken at its word and gets
 * no fallback, so the board never picks up its own tool buttons twice.
 */
export function stopsIn(root: HTMLElement = activeRoot()): HTMLElement[] {
  const declared = [...root.querySelectorAll<HTMLElement>("[data-stop]")];
  if (declared.length > 0) return declared;
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)];
}

/**
 * The stop id for an element, declared or derived.
 *
 * A derived id has to survive a re-render, because the lobby re-renders on
 * every long-poll return -- roughly once a second while somebody else is
 * choosing a deck. So it is built from what the element *is* rather than from
 * where it happens to sit: its test id, then its own id, then its accessible
 * name. The index is only a tiebreak for the genuinely identical ones (a pod
 * has three "Invite a player" buttons), and it is last precisely because it is
 * the only part that moves.
 */
export function stopIdOf(el: HTMLElement, index: number): string {
  const declared = el.dataset.stop;
  if (declared) return declared;
  const testId = el.getAttribute("data-testid");
  if (testId) return `ui:${testId}`;
  if (el.id) return `ui:#${el.id}`;
  const name = (el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 32);
  return name ? `ui:${name}:${index}` : `ui:${index}`;
}

/**
 * ON SCREEN, NOT MERELY LAID OUT.
 *
 * `getBoundingClientRect` reports an element's own box even when an ancestor
 * has clipped it out of existence -- and this layout does exactly that. An
 * opponent's lanes are `height: 0; overflow: hidden` on a handheld, because
 * their cards have to stay in the document for `FxLayer` to anchor damage
 * numerals and exit ghosts to (`styles/handheld.css`), and the seat swap adds
 * a second surface with the same property.
 *
 * A zero-size check alone does not see any of that: a card inside a zero-height
 * clipping parent still reports its own full box, so **the ring could walk onto
 * a card nobody can see**, and every gate agreed it was fine because
 * `handheldAssert`'s `unreachable` calls this very function.
 *
 * `e2e/handheldAssert.ts` has had the correct walk since Loop 3 -- it was
 * written there after the gate reported 22 cards below the card floor, all of
 * them inside a box with no height. This is the same walk, on the side that
 * decides where the ring may go rather than the side that grades it. The two
 * being different is what let the bug hide.
 *
 * Cheap enough: it runs per press, not per frame, and only walks ancestors
 * that actually clip.
 */
const CLIPS = new Set(["hidden", "clip", "auto", "scroll", "overlay"]);

/**
 * Whether an ancestor's overflow actually clips.
 *
 * Asked as "is it one of the clipping keywords" rather than "is it not
 * `visible`", and that distinction is not pedantry: jsdom returns `""` for an
 * overflow nobody set, so the negative form treats every ancestor as a clipper
 * -- and since jsdom also reports a zero box for `<body>`, every stop in every
 * component test would have been filtered out. The positive form is also the
 * more honest question, because `visible` is not the only non-clipping value a
 * browser can return.
 */
function clips(style: CSSStyleDeclaration): boolean {
  // The shorthand is read too, because jsdom does not always expand it into
  // the longhands. A browser resolves all three, so this costs nothing there.
  return CLIPS.has(style.overflowX) || CLIPS.has(style.overflowY) || CLIPS.has(style.overflow);
}

/**
 * Whether an ancestor is a box somebody can SCROLL, as opposed to one that
 * simply cuts its content off.
 *
 * The distinction is the difference between "you cannot see this" and "you
 * cannot see this YET", and the ring has to treat them oppositely. A deck
 * eleven rows down `.cat__body` is a perfectly good place for the ring to go --
 * `keepInView` brings it into view on arrival -- whereas a card inside the
 * board's `height: 0` opponent lanes is not, and `onScreen`'s whole existence
 * is that second case.
 *
 * `auto`/`scroll` only, never `hidden` or `clip`: a zero-height box with
 * content in it reports `scrollHeight > clientHeight` too, so asking about the
 * overflow *amount* alone would let every clipped lane back in and undo the bug
 * this file's header describes. And `clientHeight > 0`, because a scroller with
 * no height is not one.
 */
function scrollable(a: Element, style: CSSStyleDeclaration): { x: boolean; y: boolean } {
  const CAN = new Set(["auto", "scroll", "overlay"]);
  return {
    x: CAN.has(style.overflowX) && a.clientWidth > 0 && a.scrollWidth > a.clientWidth,
    y: CAN.has(style.overflowY) && a.clientHeight > 0 && a.scrollHeight > a.clientHeight,
  };
}

function onScreen(el: Element, rect: DOMRect): boolean {
  if (rect.width <= 0 || rect.height <= 0) return false;
  for (let a = el.parentElement; a; a = a.parentElement) {
    const style = getComputedStyle(a);
    if (!clips(style)) continue;
    const clip = a.getBoundingClientRect();
    if (clip.width <= 0 || clip.height <= 0) return false;
    const scroll = scrollable(a, style);
    const acrossX = rect.right > clip.left && rect.left < clip.right;
    const acrossY = rect.bottom > clip.top && rect.top < clip.bottom;
    if (!(acrossX || scroll.x)) return false;
    if (!(acrossY || scroll.y)) return false;
  }
  return true;
}

/**
 * Stops as scoreable candidates.
 *
 * Rects are measured fresh on every press. That sounds expensive and is not:
 * around sixty `getBoundingClientRect` calls at up to twenty-six presses a
 * second is nothing next to the thing that actually cost frame rate here, which
 * was re-rendering the board. Caching them would be a cache to invalidate on
 * every layout change the engine causes, which is all of them.
 *
 * Zero-sized stops are dropped: a card mid-`AnimatePresence`-exit reports an
 * empty box, and navigating onto one puts the ring nowhere. So are stops an
 * ancestor has clipped away -- see `onScreen`, which is the one that matters.
 */
export function candidatesIn(root: HTMLElement = activeRoot()): Candidate[] {
  const out: Candidate[] = [];
  const all = stopsIn(root);
  for (let i = 0; i < all.length; i += 1) {
    const el = all[i];
    const rect = el.getBoundingClientRect();
    if (!onScreen(el, rect)) continue;
    out.push({ id: stopIdOf(el, i), rect });
  }
  return out;
}

/**
 * The element carrying a given stop id, inside the trapped root.
 *
 * A scan rather than an attribute-value selector, and that is deliberate. An
 * action id is an opaque server string containing colons and dots, so building
 * a selector out of one needs `CSS.escape` -- which jsdom does not implement,
 * and jsdom is where every component test in this repo runs. Comparing
 * `dataset.stop` needs no escaping, cannot be injected into, and is bounded by
 * the number of stops on screen, which is the same set navigation already
 * walks on every press.
 */
export function stopElement(id: string, root: HTMLElement = activeRoot()): HTMLElement | null {
  const all = stopsIn(root);
  for (let i = 0; i < all.length; i += 1) {
    if (stopIdOf(all[i], i) === id) return all[i];
  }
  return null;
}

/** Where `dir` would take the ring from `from`, or `null` for a wall. */
export function navigate(
  from: string | null,
  dir: Dir,
  doc: Document = document,
): string | null {
  const root = activeRoot(doc);
  const candidates = candidatesIn(root);
  if (candidates.length === 0) return null;
  const current = from ? candidates.find((c) => c.id === from) : undefined;
  // With no current stop -- the ring has just appeared, or its stop went away --
  // any direction means "start somewhere" rather than "go nowhere".
  if (!current) return candidates[0].id;
  return pickStop(current.rect, candidates, dir, from ?? undefined);
}

/**
 * How near a pointer has to be to catch a stop.
 *
 * The Deck's trackpads and touchscreen arrive as ordinary mouse events via
 * Steam Input, so pointing has to work -- and a pointer that snaps is what
 * makes a trackpad usable rather than a novelty. 40px is roughly a thumb's
 * width of slack and comfortably less than the gap between two lanes.
 */
export const SNAP = 40;

/** The stop a pointer at these viewport coordinates is aiming at. */
export function stopAtPoint(x: number, y: number, doc: Document = document): string | null {
  return nearestStop(x, y, candidatesIn(stopRoot(doc)), SNAP);
}
