/**
 * Standing at somebody else's seat: whose board is on screen, guarded, and the
 * `R2` hold that borrows the same view.
 *
 * Lifted out of `Table.tsx` as it was.
 */

import { useEffect, useRef } from "react";
import type { GameView } from "../api/types";
import { useUiStore } from "./uiStore";

/** `reading` is the seat the `R2` hold is on, or null. See `useOpponentReading`. */
export function useViewingSeat(state: GameView, reading: number | null): number | null {
  const viewingPid = useUiStore((s) => s.viewingPid);
  const setViewing = useUiStore((s) => s.setViewing);

  /*
   * Whose board is actually on screen, guarded.
   *
   * A seat can leave the game while you are standing at it, and a latched pid
   * that no longer names a live player would draw an empty mat with no way back
   * -- so the guard is here rather than at the press, where it would only have
   * been true at the moment of pressing.
   */
  const viewing =
    viewingPid !== null &&
    viewingPid !== state.seat &&
    state.players[viewingPid] &&
    !state.players[viewingPid].has_lost
      ? viewingPid
      : null;

  // A new game, or leaving the table, must not arrive with somebody else's
  // board up. The store outlives the component.
  useEffect(() => () => setViewing(null), [setViewing]);

  /*
   * Holding `R2` stands you at the seat, and letting go walks you back.
   *
   * The hold used to draw a copy of their board in an overlay of its own, which
   * could only be looked at: it took no pointer, trapped no ring, repeated
   * every `data-stop` of the mat underneath it, and covered the reader. This
   * view already does all of that properly, so the hold borrows it. What was
   * on screen before the press is what the release puts back.
   */
  const viewingBeforeHold = useRef<number | null | undefined>(undefined);
  useEffect(() => {
    if (reading !== null) {
      if (viewingBeforeHold.current === undefined) {
        viewingBeforeHold.current = useUiStore.getState().viewingPid;
      }
      setViewing(reading);
    } else if (viewingBeforeHold.current !== undefined) {
      setViewing(viewingBeforeHold.current);
      viewingBeforeHold.current = undefined;
    }
  }, [reading, setViewing]);

  return viewing;
}
