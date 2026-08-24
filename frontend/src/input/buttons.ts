/**
 * The button map, and the keyboard that stands in for it.
 *
 * Indices are the W3C Standard Gamepad's, which is what a Steam Deck reports --
 * both in desktop mode and through Steam Input's virtual pad. Consumers bind
 * *named intents* and never an index, so nothing downstream can tell a pad from
 * a keyboard and there is only ever one code path to reason about.
 *
 * THE FOUR BACK GRIPS (L4/R4/L5/R5) ARE DELIBERATELY UNUSED. Steam Input maps
 * them to other buttons before the page sees anything, and a player may have
 * rebound them -- so a design that needs them is a design that breaks on
 * somebody's machine. Trackpads and gyro arrive as ordinary mouse events, which
 * is why the pointer path in `stops.ts` exists and why nothing here depends on
 * raw gyro, which the browser is never given.
 */

export type PadButton =
  | "a"
  | "b"
  | "x"
  | "y"
  | "l1"
  | "r1"
  | "l2"
  | "r2"
  | "view"
  | "menu"
  | "l3"
  | "r3"
  | "up"
  | "down"
  | "left"
  | "right";

/** W3C Standard Gamepad button indices. */
export const BTN: Record<PadButton, number> = {
  a: 0,
  b: 1,
  x: 2,
  y: 3,
  l1: 4,
  r1: 5,
  l2: 6,
  r2: 7,
  view: 8,
  menu: 9,
  l3: 10,
  r3: 11,
  up: 12,
  down: 13,
  left: 14,
  right: 15,
};

/** The four that autorepeat while held. */
export const REPEATS: ReadonlySet<PadButton> = new Set(["up", "down", "left", "right"]);

/**
 * The keyboard fallback.
 *
 * Two jobs, and the second is the one that matters. It lets the controller
 * design be reviewed and tested without a controller -- Playwright cannot
 * synthesise a real Gamepad, so this is the only route the e2e suite has into
 * the ring, the trap and the repeat ramp. And it means a keyboard player gets
 * the focus ring too, which is a plain accessibility win the app did not have.
 *
 * DELIBERATELY NOT MAPPED: the keys `Table.tsx` already owns. `Space` is pass,
 * `1`-`9` play the nth card, `g`/`e`/`c` peek, `u` undoes. Those are a keyboard
 * player's existing shortcuts and remapping them onto pad intents would break
 * the one input method that already worked.
 *
 * `Escape` IS mapped, and it is the exception that proves the rule. It used to
 * be handled in `Table` -- cancelling targeting and closing the zone viewer in
 * one go -- while `B` did the same job through a different code path. Two
 * implementations of one button is exactly the drift this map exists to stop,
 * so `Escape`, `Backspace` and `B` are now one thing: a strict unwind.
 */
export const KEYS: Record<string, PadButton> = {
  ArrowUp: "up",
  ArrowDown: "down",
  ArrowLeft: "left",
  ArrowRight: "right",
  w: "up",
  s: "down",
  a: "left",
  d: "right",
  Enter: "a",
  j: "a",
  Escape: "b",
  Backspace: "b",
  k: "b",
  x: "x",
  i: "y",
  // `[` and `]` rather than `q`/`e`: `e` is already the exile peek in
  // `Table.tsx`, so binding it here made one key both jump a zone and open a
  // modal. Bracket keys are adjacent, unclaimed, and read as "step sideways".
  "[": "l1",
  "]": "r1",
  // `z` and `v` rather than `1`/`3`: the digits play the nth card in hand and
  // have since before any of this existed.
  z: "l2",
  v: "r2",
  Tab: "view",
  "\\": "menu",
};

/**
 * Keys the browser would otherwise act on itself.
 *
 * `Tab` moves focus, which would fight the cursor for which element is focused.
 * `Backspace` is a history step in some contexts and is not recoverable. Every
 * other key in the map is allowed to bubble, because suppressing keys nobody
 * asked us to suppress is how a text field stops working.
 */
export const SWALLOW = new Set(["Tab", "Backspace"]);

/** Human labels, for the hint bar's keyboard mode. */
export const KEY_LABEL: Partial<Record<PadButton, string>> = {
  a: "Enter",
  b: "Esc",
  x: "X",
  y: "I",
  l1: "[",
  r1: "]",
  l2: "Z",
  r2: "V",
  view: "Tab",
  menu: "\\",
  up: "↑",
  down: "↓",
  left: "←",
  right: "→",
};

/**
 * What each button is drawn as in pad mode.
 *
 * Text on a disc rather than an image: the Deck's own face buttons are literally
 * lettered A B X Y in that layout, so the letter *is* the icon, and an SVG
 * sprite would be a network request and a licensing question for no gain.
 */
export const PAD_LABEL: Record<PadButton, string> = {
  a: "A",
  b: "B",
  x: "X",
  y: "Y",
  l1: "L1",
  r1: "R1",
  l2: "L2",
  r2: "R2",
  view: "⧉",
  menu: "☰",
  l3: "L3",
  r3: "R3",
  up: "↑",
  down: "↓",
  left: "←",
  right: "→",
};
