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
  return (
    app.querySelector<HTMLElement>(".wheelwrap") ??
    app.querySelector<HTMLElement>("[data-modal-root]:not([data-closing])") ??
    app
  );
}

/**
 * What counts as focusable when nothing has declared itself a stop.
 *
 * Excludes `[tabindex="-1"]` and disabled controls: a control the player cannot
 * press is not somewhere the ring should be able to rest.
 */
const FOCUSABLE =
  'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

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
export function stopsIn(root: HTMLElement = stopRoot()): HTMLElement[] {
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

function onScreen(el: Element, rect: DOMRect): boolean {
  if (rect.width <= 0 || rect.height <= 0) return false;
  for (let a = el.parentElement; a; a = a.parentElement) {
    if (!clips(getComputedStyle(a))) continue;
    const clip = a.getBoundingClientRect();
    if (clip.width <= 0 || clip.height <= 0) return false;
    const intersects =
      rect.right > clip.left &&
      rect.left < clip.right &&
      rect.bottom > clip.top &&
      rect.top < clip.bottom;
    if (!intersects) return false;
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
export function candidatesIn(root: HTMLElement = stopRoot()): Candidate[] {
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
export function stopElement(id: string, root: HTMLElement = stopRoot()): HTMLElement | null {
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
  const root = stopRoot(doc);
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
