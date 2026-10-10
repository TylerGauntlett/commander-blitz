/**
 * A staged attacker leans toward the seat it is aimed at.
 *
 * Lifted out of `Table.tsx` as it was; `boardRef` is the table body every
 * effect coordinate is measured from.
 */

import { type RefObject, useEffect } from "react";
import { drive } from "./actuators";

export function useAttackLean(
  stagedAttacks: Record<number, number>,
  boardRef: RefObject<HTMLDivElement | null>,
): void {
  /*
   * A staged attacker leans toward the seat it is aimed at, and holds.
   *
   * The amber rim says "selected"; the lean says "aimed at *them*", which in a
   * pod is a different fact and the one that matters -- three creatures staged
   * at three different players look identical under a rim alone.
   *
   * Driven from an effect rather than from the click handler because staging
   * has four entry points (the card, the panel row, the defender chip, and
   * undo), and one of them is the server sending a state where nothing is
   * staged any more. Reconciling from the current staging covers all four.
   */
  useEffect(() => {
    const staged = Object.entries(stagedAttacks);
    if (staged.length === 0) return;
    const board = boardRef.current?.getBoundingClientRect();
    if (!board) return;
    for (const [oid, defender] of staged) {
      const seat = document.querySelector(`[data-player="${defender}"]`);
      if (!seat) continue;
      const box = seat.getBoundingClientRect();
      drive(Number(oid))?.lean({
        x: box.left + box.width / 2 - board.left,
        y: box.top + box.height / 2 - board.top,
      });
    }
    // Released on unstage, on commit, and on unmount -- `rest` is the same
    // cancel path every transient uses, so the hold needs no special teardown.
    return () => {
      for (const [oid] of staged) drive(Number(oid))?.rest();
    };
  }, [stagedAttacks, boardRef]);
}
