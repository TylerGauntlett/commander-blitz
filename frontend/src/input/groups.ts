/**
 * The board's five regions, and jumping between them.
 *
 * ## Why a group is a container and not a stop-id prefix
 *
 * `card:<oid>` is a hand card, a board card, a stack item AND a prompt option.
 * The namespace deliberately says what a stop *is* rather than where it lives,
 * because a permanent keeps its id when it changes zone -- which is the whole
 * reason the ring survives a re-render. So the id cannot tell you which region
 * you are in, and asking the DOM is not a shortcut here, it is the question.
 *
 * ## Why this exists at all
 *
 * At 1280x800 the ring has to cross a 96px seat strip, three lanes, a fanned
 * hand and a 243px rail, and directional navigation crosses them one card at a
 * time. `docs/handheld-playtest.md` Loop 1 records walking the board as "a bad
 * way to ask can you reach everything" -- reachable and reachable-in-under-a-
 * second are different properties, and only the second is playable.
 *
 * `HintBar` has advertised `L1 Zone` since it was written and **nothing has
 * ever been bound to it**. So has `L2 Menu`, and `verbsFor` returns `Y Read` on
 * every card stop. This module is the first of those three kept.
 *
 * ## The trap is subordinate to the modal trap
 *
 * A group traps the ring inside a region so a thumb-flick does not throw it
 * across the screen. A modal traps it inside a dialog so it cannot press things
 * underneath one. The second always wins -- see `activeRoot`.
 */

export type GroupId = "hand" | "acts" | "seats" | "orb" | "board";

interface Group {
  id: GroupId;
  /** The container, as the app's own class names. */
  sel: string;
  /** What the dial calls it. */
  label: string;
}

/**
 * In the order `R1` walks them, which is roughly the order a turn is spent in:
 * what you can play, what you can do with it, who you would do it to, what you
 * have, and what is already down.
 */
export const GROUPS: readonly Group[] = [
  { id: "hand", sel: ".hand", label: "Hand" },
  { id: "acts", sel: ".rail--right", label: "Actions" },
  { id: "seats", sel: ".play__opponents", label: "Opponents" },
  { id: "orb", sel: ".play__mine .mat__side", label: "You" },
  { id: "board", sel: ".play__mine .mat__lanes", label: "Board" },
] as const;

/** The container for a group, or `null` when the board is not on screen. */
export function groupRoot(id: GroupId, doc: Document = document): HTMLElement | null {
  const group = GROUPS.find((candidate) => candidate.id === id);
  if (!group) return null;
  return doc.querySelector<HTMLElement>(group.sel);
}

/**
 * A stop nobody can see is not a stop.
 *
 * The same ancestor-clip walk `stops.ts` and the gates use, restated rather
 * than exported from there because it is two lines and exporting it would make
 * the two files depend on each other in both directions.
 */
function visible(el: Element): boolean {
  const box = el.getBoundingClientRect();
  if (box.width <= 0 || box.height <= 0) return false;
  for (let a = el.parentElement; a; a = a.parentElement) {
    const style = getComputedStyle(a);
    const clips = ["hidden", "clip", "auto", "scroll", "overlay"];
    if (
      !clips.includes(style.overflowX) &&
      !clips.includes(style.overflowY) &&
      !clips.includes(style.overflow)
    ) {
      continue;
    }
    const clip = a.getBoundingClientRect();
    if (clip.width <= 0 || clip.height <= 0) return false;
    if (
      box.right <= clip.left ||
      box.left >= clip.right ||
      box.bottom <= clip.top ||
      box.top >= clip.bottom
    ) {
      return false;
    }
  }
  return true;
}

/**
 * The groups that are on screen and hold something to land on.
 *
 * A group whose container is missing or empty is NOT a destination. An empty
 * hand that you could still cycle into would take the ring somewhere with
 * nothing in it -- and the ring going out is the failure `ringLost` exists to
 * catch, arriving by a route the player asked for. On a handheld the opponents'
 * lanes are clipped to zero height and their cards are still in the document,
 * which is exactly why the check is on visibility rather than on presence.
 */
export function groupsPresent(doc: Document = document): GroupId[] {
  const out: GroupId[] = [];
  for (const group of GROUPS) {
    const root = doc.querySelector<HTMLElement>(group.sel);
    if (!root) continue;
    const stops = [...root.querySelectorAll<HTMLElement>("[data-stop]")];
    if (stops.some(visible)) out.push(group.id);
  }
  return out;
}

/** Which group an element is in, or `null` if it is in none of them. */
export function groupOf(el: Element, doc: Document = document): GroupId | null {
  for (const group of GROUPS) {
    const root = doc.querySelector(group.sel);
    if (root?.contains(el)) return group.id;
  }
  return null;
}

/**
 * The next group along, wrapping, skipping the ones that are not there.
 *
 * From `null` -- the ring has not been in a group yet -- forwards means the
 * first present group and backwards means the last, so the very first press
 * always lands somewhere rather than doing nothing.
 */
export function nextGroup(
  current: GroupId | null,
  step: 1 | -1,
  doc: Document = document,
): GroupId | null {
  const present = groupsPresent(doc);
  if (present.length === 0) return null;
  if (current === null) return step === 1 ? present[0] : present[present.length - 1];
  const at = present.indexOf(current);
  if (at === -1) return step === 1 ? present[0] : present[present.length - 1];
  return present[(at + step + present.length) % present.length];
}

/* ==========================================================================
   The current group, as module state
   ==========================================================================

   A singleton and not React state, for the same measured reason `cursor.ts` is
   one: thirty components subscribing to what the ring is doing cost 18.5fps
   against 59.7 under a 4x throttle. Nothing on the board needs to re-render
   because the ring moved to a different region -- the trap is read at press
   time, and the only thing that wants to *draw* differently is a dim on the
   inactive regions, which CSS can do from an attribute.
   ========================================================================== */

let current: GroupId | null = null;
const listeners = new Set<() => void>();

export function getGroup(): GroupId | null {
  return current;
}

/**
 * Enter a group.
 *
 * Writes `data-group` to `<html>`, so the stylesheet can say which region owns
 * the ring without a single component subscribing. A trap you cannot see is a
 * wall you cannot explain, and the first version of this had no mark at all --
 * pressing a direction into the edge of a region simply did nothing.
 */
export function setGroup(id: GroupId | null): void {
  if (current === id) return;
  current = id;
  if (typeof document !== "undefined") {
    const root = document.documentElement;
    if (id) root.setAttribute("data-group", id);
    else root.removeAttribute("data-group");
  }
  for (const listener of listeners) listener();
}

export function subscribeGroup(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Between tests, and between games. */
export function resetGroups(): void {
  current = null;
  if (typeof document !== "undefined") {
    document.documentElement.removeAttribute("data-group");
  }
  remembered.clear();
}

/* ==========================================================================
   Where you were, per group
   ========================================================================== */

const remembered = new Map<GroupId, string>();

/**
 * Remember the stop the ring was on when it left a group.
 *
 * Coming back to the hand and landing on the card you were reading is the
 * difference between a jump and a reset. Keyed by stop id rather than by index,
 * for the reason the whole namespace is: `card:14` is the same card whether it
 * is drawn first in its lane or last.
 */
export function rememberStop(id: GroupId, stop: string): void {
  remembered.set(id, stop);
}

export function rememberedStop(id: GroupId): string | undefined {
  return remembered.get(id);
}
