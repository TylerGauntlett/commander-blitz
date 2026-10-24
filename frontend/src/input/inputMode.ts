/**
 * What the player is holding, and therefore which controls to draw.
 *
 * Three facts now, and the third is the one a Steam Deck forced:
 *
 *   pref          what the player CHOSE, if they chose: auto, pad, keyboard, mouse, touch
 *   mode          what they last actually used: mouse, keyboard, pad or touch
 *   padConnected  whether a gamepad exists at all
 *
 * `mode` is LAST-INPUT-WINS rather than "is a pad plugged in", because a Deck in
 * desktop mode has a mouse and a pad attached at once, and so does anybody
 * playing at a desk with a controller in their lap. Which one they are holding
 * is a question only their most recent action can answer.
 *
 * ## Why there is a preference at all
 *
 * A STEAM DECK IN GAMING MODE IS A CONTROLLER THAT ARRIVES AS A KEYBOARD.
 *
 * Steam Input applies a controller layout to every non-Steam shortcut, and it
 * detects browsers and picks a keyboard/mouse template for them. Under that
 * layout the pad is grabbed exclusively, no virtual gamepad is published, and
 * `navigator.getGamepads()` is empty -- while the d-pad arrives as arrow keys
 * and A arrives as Enter. Every signal this module had said "keyboard", so the
 * hint bar told a player holding a controller to press Enter and Esc.
 *
 * It cannot always be inferred, so it can also be said: `setScheme` pins the
 * answer, the front door's Settings card is where a player says it, and the
 * choice persists. `auto` is the default and covers the ordinary cases.
 *
 * ## Why this is an attribute on `<html>` and not React state
 *
 * The whole requirement is "a mouse player never sees a controller hint". If
 * every `Glyph` subscribed to a hook, moving the mouse would re-render the
 * board -- which is the same trap `input/cursor.ts` documents at length, one
 * level up. So this writes attributes on the root element and the answer is
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
 * glyphs. Neither implies the other -- except in one narrow place, `padShaped`
 * below, where the viewport is used as a GUARD rather than as a signal.
 */

import { HANDHELD_QUERY } from "../logic/breakpoints";

export type InputMode = "mouse" | "keyboard" | "pad" | "touch";

/** What the player chose. `auto` means "work it out", and is the default. */
export type SchemePref = "auto" | "pad" | "keyboard" | "mouse" | "touch";

/**
 * Whether a mode points at things itself, so no ring is drawn and no region
 * traps it. A finger is its own pointer, exactly as a mouse is (ADR 0025).
 */
export function isPointerMode(mode: InputMode | string | null): boolean {
  return mode === "mouse" || mode === "touch";
}

const SCHEMES: readonly SchemePref[] = ["auto", "pad", "keyboard", "mouse", "touch"];

const SCHEME_KEY = "commanderblitz.scheme";

let pref: SchemePref = "auto";
let mode: InputMode = "mouse";
let padConnected = false;
let started = false;
/** Undoes `startInputMode`'s listeners, for `resetInputMode`. */
let unbind: (() => void) | null = null;

type Listener = () => void;
const listeners = new Set<Listener>();

/**
 * How long to ignore further pointer movement after recording one.
 *
 * A mouse resting on a desk emits `pointermove` from vibration alone, and a
 * mode write per event would churn the attribute.
 */
const MOVE_THROTTLE = 200;
/*
 * NEGATIVE INFINITY RATHER THAN ZERO, because zero is a real reading.
 *
 * `performance.now()` starts at 0 on a fresh document -- and under fake timers
 * it sits there -- so a sentinel of 0 means "never happened" and "happened at
 * the very first instant" are the same value. The grace below was skipped
 * outright for any input in the first tick, which is exactly when a test, and a
 * player on a freshly loaded page, does everything.
 */
let lastMove = Number.NEGATIVE_INFINITY;

/**
 * How long a key or pad press owns the mode against mere pointer MOVEMENT.
 *
 * THE DECK'S RIGHT STICK AND TRACKPADS ARE MOUSE EVENTS. Steam Input presents
 * both as ordinary pointer input, so a thumb resting on a trackpad emitted
 * `pointermove` forever -- and one of those flipped the mode to `mouse`, which
 * hides the ring, blanks every glyph, hides the hint bar, and drops the region
 * trap. The controller appeared to die mid-game for touching the device it is
 * built into.
 *
 * A pointer PRESS is never graced: clicking is unambiguous, and somebody who
 * clicks has chosen the mouse. This is only about drift.
 */
const POINTER_GRACE = 1500;
let lastDirected = Number.NEGATIVE_INFINITY;

/**
 * The keys a controller pretending to be a keyboard can produce.
 *
 * Steam's keyboard templates bind a d-pad to the arrows and the face buttons to
 * Enter/Escape, so a session driven by a disguised pad emits these and nothing
 * else. A session driven by a real keyboard types: a seat name, a pod code, `g`
 * to peek, a digit to play a card.
 */
const NAV_KEYS = new Set([
  "ArrowUp",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
  "Enter",
  "Escape",
  "Backspace",
  "Tab",
]);

/** How many nav keys, with no character key, before we believe it is a pad. */
const NAV_STREAK = 3;

let navKeys = 0;
let charKeys = 0;

function now(): number {
  return typeof performance !== "undefined" ? performance.now() : 0;
}

/**
 * Whether keyboard-shaped input is really a controller.
 *
 * Two ways to be sure and one way to guess:
 *
 *   - a pad is genuinely connected, and is also sending keys (Steam layouts
 *     that publish a virtual pad AND emit keystrokes do exactly this)
 *   - the session has produced `NAV_STREAK` navigation keys and not one
 *     character key
 *
 * THE VIEWPORT GATE IS LOAD-BEARING ON THE SECOND. A desktop keyboard user who
 * happens to arrow around a menu must never be told to press "A" -- they have no
 * A. So the guess is only made at handheld size, which is what a Deck's 1280x800
 * is and what a 1920x1080 desktop is not. It is the one place in this module
 * where the layout signal is consulted, and it is a veto rather than a vote.
 *
 * `charKeys` is a permanent disqualifier rather than a window: the moment
 * somebody types a letter, they have a keyboard, and no later run of arrows
 * should undo that.
 */
function padShaped(): boolean {
  if (padConnected) return true;
  if (charKeys > 0 || navKeys < NAV_STREAK) return false;
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia(HANDHELD_QUERY).matches;
}

/** The mode actually written to the document, preference and disguise applied. */
function resolved(): InputMode {
  if (pref !== "auto") return pref;
  if (mode === "keyboard" && padShaped()) return "pad";
  return mode;
}

function announce(): void {
  for (const listener of listeners) listener();
}

/**
 * Write the resolved mode, and say whether it actually moved.
 *
 * AGAINST WHAT WAS WRITTEN, never against a freshly recomputed "before".
 *
 * `resolved()` reads the heuristic's counters, and the counters are bumped by
 * the very keypress that then calls `noteInput` -- so a "before" computed inside
 * `noteInput` already had the new answer in it. The press that completed the
 * streak therefore compared pad against pad, concluded nothing had changed, and
 * returned without writing: `getInputMode()` said `pad` while `<html>` still
 * said `keyboard`, and since every glyph in the app is drawn from the attribute,
 * the hint bar went on showing Enter and Esc. The state and the picture
 * disagreeing is the worst shape this bug could have taken, because the one
 * thing anybody would check says it is fixed.
 */
let applied: InputMode | null = null;

function apply(): boolean {
  const next = resolved();
  if (typeof document === "undefined") {
    applied = next;
    return false;
  }
  const root = document.documentElement;
  root.toggleAttribute("data-pad", padConnected);
  if (next === applied && root.getAttribute("data-input") === next) return false;
  root.setAttribute("data-input", next);
  applied = next;
  return true;
}

export function getInputMode(): InputMode {
  return resolved();
}

/** What was last physically used, ignoring the preference. For diagnostics. */
export function getRawInputMode(): InputMode {
  return mode;
}

export function isPadConnected(): boolean {
  return padConnected;
}

export function getScheme(): SchemePref {
  return pref;
}

/** Pin the control scheme, or hand it back to `auto`. Persists. */
export function setScheme(next: SchemePref): void {
  if (next === pref) return;
  pref = next;
  try {
    if (next === "auto") localStorage.removeItem(SCHEME_KEY);
    else localStorage.setItem(SCHEME_KEY, next);
  } catch {
    // Private mode. The choice still holds for this session.
  }
  if (apply()) announce();
}

export function subscribeInputMode(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * Record what was just used.
 *
 * Exported because `pad.ts` calls it on a real button edge and on stick motion
 * -- the pad is polled rather than evented, so this module cannot observe it
 * from here without a second loop.
 */
export function noteInput(next: InputMode): void {
  if (next === "keyboard" || next === "pad") lastDirected = now();
  mode = next;
  if (apply()) announce();
}

export function notePadConnected(connected: boolean): void {
  if (connected === padConnected) return;
  padConnected = connected;
  // Always announced: `data-pad` moved even when `data-input` did not, and a
  // subscriber asking `isPadConnected` has a new answer either way.
  apply();
  announce();
}

/** What the `auto` heuristic currently believes, for the settings panel. */
export function schemeDiagnostics(): {
  pref: SchemePref;
  resolved: InputMode;
  raw: InputMode;
  padConnected: boolean;
  navKeys: number;
  charKeys: number;
  padShaped: boolean;
} {
  return {
    pref,
    resolved: resolved(),
    raw: mode,
    padConnected,
    navKeys,
    charKeys,
    padShaped: padShaped(),
  };
}

function storedScheme(): SchemePref {
  try {
    const saved = localStorage.getItem(SCHEME_KEY);
    if (saved && saved !== "auto" && SCHEMES.includes(saved as SchemePref)) {
      return saved as SchemePref;
    }
  } catch {
    // Private mode, or no DOM at all under vitest. `auto` is fine.
  }
  return "auto";
}

/**
 * `?input=pad`, which is the escape hatch for a device where nothing else works.
 *
 * Deliberately not persisted: a URL is how you TRY something. The Settings card
 * is how you keep it.
 */
function urlScheme(): SchemePref | null {
  try {
    const value = new URLSearchParams(window.location.search).get("input");
    if (value && SCHEMES.includes(value as SchemePref)) return value as SchemePref;
  } catch {
    // No location, or a URL the parser refuses. Not worth a failure.
  }
  return null;
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
  pref = urlScheme() ?? storedScheme();
  apply();

  const onPointer = (event: PointerEvent) => {
    /*
     * A FINGER IS TOUCH, NOT A MOUSE (ADR 0025).
     *
     * A touch press writes `touch`, and a move made by a finger writes
     * nothing: a drag across the hand is still the same finger. Neither a
     * touch nor a mouse draws a ring or a glyph, but they differ in what a tap
     * on a card means -- a finger cannot hover, so a tap selects a card a click
     * would only have pointed at. A pen hovers like a mouse, and is one.
     */
    if (event.pointerType === "touch") {
      if (event.type === "pointerdown") noteInput("touch");
      return;
    }
    if (event.type === "pointermove") {
      const at = now();
      if (at - lastMove < MOVE_THROTTLE) return;
      lastMove = at;
      // Drift does not outrank a recent press -- see `POINTER_GRACE`.
      if (at - lastDirected < POINTER_GRACE) return;
    }
    noteInput("mouse");
  };
  const onKey = (event: KeyboardEvent) => {
    /*
     * Counted before the mode is written, so the very press that completes the
     * streak is already the one the resolver sees.
     *
     * Modifiers are neither: holding Shift to capitalise is not a character and
     * not a navigation, and counting it as a character would disqualify a pad
     * whose layout sends one.
     */
    if (event.key.length > 1 && !NAV_KEYS.has(event.key)) {
      // F-keys, Meta, Alt, Home, PageDown... none of them tell us anything.
    } else if (NAV_KEYS.has(event.key)) {
      navKeys += 1;
    } else {
      charKeys += 1;
    }
    noteInput("keyboard");
  };

  window.addEventListener("pointerdown", onPointer, { capture: true, passive: true });
  window.addEventListener("pointermove", onPointer, { capture: true, passive: true });
  window.addEventListener("keydown", onKey, { capture: true, passive: true });
  // Kept so `resetInputMode` can genuinely undo this. Without it a suite that
  // resets between tests stacks a fresh set of listeners each time, and one
  // keypress then counts three or four times against the `auto` heuristic.
  unbind = () => {
    window.removeEventListener("pointerdown", onPointer, true);
    window.removeEventListener("pointermove", onPointer, true);
    window.removeEventListener("keydown", onKey, true);
  };
}

/** Test seam. */
export function resetInputMode(): void {
  unbind?.();
  unbind = null;
  pref = "auto";
  mode = "mouse";
  padConnected = false;
  lastMove = Number.NEGATIVE_INFINITY;
  lastDirected = Number.NEGATIVE_INFINITY;
  applied = null;
  navKeys = 0;
  charKeys = 0;
  started = false;
  listeners.clear();
  if (typeof document !== "undefined") {
    document.documentElement.removeAttribute("data-input");
    document.documentElement.removeAttribute("data-pad");
  }
}
