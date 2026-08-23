/**
 * What the player is holding, and therefore which controls to draw.
 *
 * Two facts, deliberately independent:
 *
 *   mode          what they last actually used: mouse, keyboard, or pad
 *   padConnected  whether a gamepad exists at all
 *
 * `mode` is LAST-INPUT-WINS rather than "is a pad plugged in", because a Deck in
 * desktop mode has a mouse and a pad attached at once, and so does anybody
 * playing at a desk with a controller in their lap. Which one they are holding
 * is a question only their most recent action can answer.
 *
 * ## Why this is an attribute on `<html>` and not React state
 *
 * The whole requirement is "a mouse player never sees a controller hint". If
 * every `Glyph` subscribed to a hook, moving the mouse would re-render the
 * board -- which is the same trap `input/cursor.ts` documents at length, one
 * level up. So this writes two attributes on the root element and the answer is
 * a CSS question:
 *
 *     html[data-input="pad"]      .glyph--pad { display: inline-grid }
 *     html[data-input="keyboard"] .glyph--key { display: inline-grid }
 *
 * Zero React work per pointer move, and the hints are correct before the next
 * paint rather than after the next commit.
 *
 * This is also **independent of the layout signal**. `logic/breakpoints.ts`
 * decides handheld-vs-desktop from the viewport alone. A player at a 4K monitor
 * who picks up a controller gets the ring and the glyphs on the unchanged
 * three-column board; a Deck user with no pad gets the compact layout and no
 * glyphs. Neither implies the other.
 */

export type InputMode = "mouse" | "keyboard" | "pad";

let mode: InputMode = "mouse";
let padConnected = false;
let started = false;

type Listener = () => void;
const listeners = new Set<Listener>();

/**
 * How long to ignore further pointer movement after recording one.
 *
 * A mouse resting on a desk emits `pointermove` from vibration alone, and a
 * mode write per event would churn the attribute -- and, worse, would flip the
 * mode back to mouse in the middle of somebody navigating with a pad next to a
 * nudged mouse. A pointer *press* is never throttled: that is unambiguous.
 */
const MOVE_THROTTLE = 200;
let lastMove = 0;

function announce(): void {
  for (const listener of listeners) listener();
}

function apply(): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.setAttribute("data-input", mode);
  root.toggleAttribute("data-pad", padConnected);
}

export function getInputMode(): InputMode {
  return mode;
}

export function isPadConnected(): boolean {
  return padConnected;
}

export function subscribeInputMode(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * Record what was just used.
 *
 * Exported because `pad.ts` calls it on a real button edge -- the pad is polled
 * rather than evented, so this module cannot observe it from here without a
 * second loop.
 */
export function noteInput(next: InputMode): void {
  if (next === mode) return;
  mode = next;
  apply();
  announce();
}

export function notePadConnected(connected: boolean): void {
  if (connected === padConnected) return;
  padConnected = connected;
  apply();
  announce();
}

/**
 * Begin watching. Idempotent, because several roots may mount over a session.
 *
 * Listeners are passive and on the capture phase: this only observes, and
 * observing must never be able to interfere with a control's own handling.
 */
export function startInputMode(): void {
  if (started || typeof window === "undefined") return;
  started = true;
  apply();

  const onPointer = (event: PointerEvent) => {
    // A touch is not a mouse, but it is not a pad either, and it wants the same
    // thing a mouse does: no button glyphs, because there are no buttons.
    if (event.type === "pointermove") {
      const now = performance.now();
      if (now - lastMove < MOVE_THROTTLE) return;
      lastMove = now;
    }
    noteInput("mouse");
  };
  const onKey = () => noteInput("keyboard");

  window.addEventListener("pointerdown", onPointer, { capture: true, passive: true });
  window.addEventListener("pointermove", onPointer, { capture: true, passive: true });
  window.addEventListener("keydown", onKey, { capture: true, passive: true });
}

/** Test seam. */
export function resetInputMode(): void {
  mode = "mouse";
  padConnected = false;
  lastMove = 0;
  listeners.clear();
  if (typeof document !== "undefined") {
    document.documentElement.removeAttribute("data-input");
    document.documentElement.removeAttribute("data-pad");
  }
}
