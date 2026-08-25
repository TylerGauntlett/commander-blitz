/**
 * Counting presses.
 *
 * The controller work is about pacing, and pacing has a number: how many button
 * presses a core journey costs. Every other gate in this suite answers "can a
 * controller reach this" -- `unreachableStops`, the hit floor, the region trap.
 * None of them can answer "and how long does it take", which is the property a
 * player actually feels, and which regresses silently: a stop added to a lane, a
 * region entered on the wrong side, a ring left on a card that moved zones, and
 * a two-press decision is a nine-press one with nothing failing.
 *
 * So a journey is walked with the same synthetic keys the rest of the pad tests
 * use -- `input/buttons.ts:KEYS` is the only route a test has into the ring,
 * because neither Playwright nor Vitest can synthesise a real `Gamepad` -- and
 * the press count is asserted against a budget.
 *
 * ## A budget, not an exact figure
 *
 * `expect(cost).toBeLessThanOrEqual(n)`, always. An exact count would fail on
 * any improvement, which is the wrong direction to be strict in; a ceiling
 * fails only when a journey gets *worse*, which is the regression worth
 * catching. The number in each story is the count measured against the real
 * engine at 1280x800 and written down.
 */

import { userEvent } from "storybook/test";
import type { PadButton } from "../input/buttons";
import { getCursor } from "../input/cursor";

/**
 * The keystroke that stands in for each button.
 *
 * Mirrors `input/buttons.ts:KEYS` rather than restating it in spirit -- if a
 * binding moves there, the journeys move with it. Two are escaped for
 * `userEvent`'s grammar: `[` opens a key descriptor, so a literal bracket is
 * doubled, and every named key is braced.
 */
export const STROKE: Record<PadButton, string> = {
  up: "{ArrowUp}",
  down: "{ArrowDown}",
  left: "{ArrowLeft}",
  right: "{ArrowRight}",
  a: "{Enter}",
  b: "{Escape}",
  x: "x",
  y: "i",
  l1: "[[",
  r1: "]",
  l2: "z",
  r2: "v",
  view: "{Tab}",
  menu: "\\",
  l3: "",
  r3: "",
};

export interface Journey {
  /** Press one button. Everything is one press, which is the whole point. */
  press(button: PadButton): Promise<void>;
  /** Press several, in order. */
  walk(...buttons: PadButton[]): Promise<void>;
  /** How many presses have been spent. */
  readonly cost: number;
  /** The stop the ring is on, for asserting where a journey ended. */
  at(): string | null;
  /** The region the ring is in, which is `data-group` on `<html>`. */
  region(): string | null;
  /** Every stop pressed, in order, for a failure message worth reading. */
  readonly trail: string[];
}

/** One painted frame, which is the unit the pad loop runs in. */
const frame = () => new Promise<void>((done) => requestAnimationFrame(() => done()));

/**
 * Start counting.
 *
 * The caller is responsible for `startPad()` and for mounting `useCursorNav` --
 * `Screen` does both in the app, and a story that renders `Table` alone has
 * neither, so `A` and the directions would silently do nothing. See
 * `Journeys.stories.tsx`, which mounts the hook the way the app does.
 */
export function journey(): Journey {
  let spent = 0;
  const trail: string[] = [`start ${getCursor() ?? "-"}`];
  const self: Journey = {
    async press(button) {
      const stroke = STROKE[button];
      if (!stroke) throw new Error(`${button} has no keyboard stand-in to press`);
      await userEvent.keyboard(stroke);
      /*
       * A KEY IS NOT AN INTENT UNTIL THE LOOP TICKS.
       *
       * `pad.ts:onKeyDown` adds the button to a latch and calls `wake()`; the
       * handlers fire inside the next `requestAnimationFrame`. So a press
       * followed immediately by an assertion is asserting against a board that
       * has not heard it yet -- and, worse, a second press in the same frame
       * lands on a ring that has not moved, which quietly makes a journey cost
       * whatever number was written down.
       *
       * Two frames: one for the pad loop to read the latch and dispatch, one
       * for React to commit what the handler did and for the layout effects
       * (`resolveCursor`, and the follow-up that moves the ring) to run.
       */
      await frame();
      await frame();
      spent += 1;
      trail.push(`${button} -> ${getCursor() ?? "-"}`);
    },
    async walk(...buttons) {
      for (const button of buttons) await self.press(button);
    },
    get cost() {
      return spent;
    },
    at: () => getCursor(),
    region: () => document.documentElement.getAttribute("data-group"),
    get trail() {
      return trail;
    },
  };
  return self;
}
