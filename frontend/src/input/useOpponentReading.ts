/**
 * Which opponent's board is being read while `R2` is held.
 *
 * The hold behind `OpponentBoard`, lifted out of `Table.tsx` as it was: an
 * analog trigger past 0.5 opens it on the seat the ring is on (or the first
 * opponent), and letting go closes it. Handheld only.
 */

import { useEffect, useRef, useState } from "react";
import { parseStop } from "../logic/verbs";
import { getCursor } from "./cursor";
import { onFrame as onPadFrame } from "./pad";

export function useOpponentReading(
  handheld: boolean,
  opponents: number[],
  seat: number,
): number | null {
  const state = { seat };
  /**
   * Which opponent is being read, while `R2` is held.
   *
   * A hold rather than a toggle: a toggle needs a second press to put away and
   * leaves the board covered if you forget, whereas letting go is not something
   * you can forget to do. `onFrame` because a trigger is analog and has no
   * press event -- 0.5 is past any resting value and well short of the click.
   *
   * The seat is whichever one the ring is on, falling back to the first
   * opponent, so "look at them" needs no separate act of choosing.
   */
  const [reading, setReading] = useState<number | null>(null);
  const readingRef = useRef<number | null>(null);
  readingRef.current = reading;

  useEffect(() => {
    if (!handheld) return;
    return onPadFrame((frame) => {
      const held = frame.r2 > 0.5;
      if (!held) {
        if (readingRef.current !== null) setReading(null);
        return;
      }
      if (readingRef.current !== null) return;
      const ref = parseStop(getCursor());
      const onSeat = ref.kind === "orb" && ref.id !== null && ref.id !== state.seat;
      setReading(onSeat ? ref.id : (opponents[0] ?? null));
    });
  }, [handheld, opponents, state.seat]);

  return reading;
}
