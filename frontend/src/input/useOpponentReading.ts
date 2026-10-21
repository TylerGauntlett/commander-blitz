/**
 * Which opponent's board is being read while `R2` is held.
 *
 * Lifted out of `Table.tsx` as it was: an analog trigger past 0.5 names an
 * opponent, and letting go names nobody. `Table` stands you at that seat for as
 * long as it is named -- the same board swap a click on the seat makes -- so its
 * cards take the pointer and the ring and show in the reader. Handheld only.
 */

import { useEffect, useRef, useState } from "react";
import { onFrame as onPadFrame } from "./pad";

/**
 * The opponent the next press reads: the one after `last` in seat order, or the
 * first when nobody has been read yet or `last` has since left the game.
 */
export function nextOpponent(opponents: readonly number[], last: number | null): number | null {
  if (opponents.length === 0) return null;
  const at = last === null ? -1 : opponents.indexOf(last);
  return opponents[(at + 1) % opponents.length];
}

export function useOpponentReading(handheld: boolean, opponents: number[]): number | null {
  /**
   * Which opponent is being read, while `R2` is held.
   *
   * A hold rather than a toggle: a toggle needs a second press to put away and
   * leaves the board covered if you forget, whereas letting go is not something
   * you can forget to do. `onFrame` because a trigger is analog and has no
   * press event -- 0.5 is past any resting value and well short of the click.
   *
   * EACH PRESS STEPS TO THE NEXT OPPONENT, in seat order, wrapping. So press,
   * release, press walks the table -- first opponent, your own board, second
   * opponent -- with no separate act of choosing. It used to read whichever
   * seat the ring was on, which in a pod meant moving the ring to an orb before
   * every look and left every seat but the first out of reach of the trigger.
   */
  const [reading, setReading] = useState<number | null>(null);
  const readingRef = useRef<number | null>(null);
  readingRef.current = reading;
  // The seat the last press read; outlives the release so the next one steps on.
  const lastRead = useRef<number | null>(null);

  useEffect(() => {
    if (!handheld) return;
    return onPadFrame((frame) => {
      const held = frame.r2 > 0.5;
      if (!held) {
        if (readingRef.current !== null) setReading(null);
        return;
      }
      if (readingRef.current !== null) return;
      const next = nextOpponent(opponents, lastRead.current);
      lastRead.current = next;
      setReading(next);
    });
  }, [handheld, opponents]);

  return reading;
}
