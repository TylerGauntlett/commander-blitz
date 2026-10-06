/**
 * The card hold: one card read full screen, and the three ways into it.
 *
 * Lifted out of `Table.tsx` as it was. `Y` opens it from `usePadBindings`; a
 * right-click and a long-press open it from here, on the table's root.
 */

import { type MouseEvent as ReactMouseEvent, useCallback, useState } from "react";
import type { GameView } from "../api/types";
import { findCard } from "../logic/zoneGrouping";
import { useUiStore } from "../state/uiStore";
import { oidAt, useLongPress } from "./longPress";

export function useCardHold(state: GameView) {
  /*
   * The card being read full screen, by oid.
   *
   * By oid and not by object, for the reason the reader in the mockup round
   * held a NAME rather than a node: the engine pushes a whole new state on
   * every action, so a card object captured here would be a snapshot that stops
   * matching the board the moment anything happens to it.
   */
  const [heldCard, setHeldCard] = useState<number | null>(null);
  const closeHold = useCallback(() => setHeldCard(null), []);

  /*
   * Right-click reads the card under the pointer, full screen.
   *
   * The desktop's way into the hold, which until now only `Y` could open --
   * and `Y`'s keyboard stand-in `i` read the ring, which a mouse player cannot
   * see. Right-click is what every digital card client uses for "show me this
   * card bigger", and it needs no new state: whatever the pointer is over has
   * already written `hoveredOid` (a card, a plinth, a panel row, a seat's
   * commander window), so this asks the rail what it is showing and opens it.
   *
   * On the table and not on each card, so every surface that fills the rail
   * gets it for free and none can drift. A right-click over nothing readable
   * falls through to the browser's own menu, untouched.
   */
  const readHovered = useCallback(
    (event: ReactMouseEvent) => {
      // The card under the click first: on a touch screen a long-press arrives
      // here as a `contextmenu` with no hover behind it. Then the rail's card.
      const oid = oidAt(event.target) ?? useUiStore.getState().hoveredOid;
      if (oid === null || findCard(state, oid) === null) return;
      event.preventDefault();
      setHeldCard(oid);
    },
    [state],
  );

  /** ...and a phone's way in, which has neither hover nor a right button. */
  const longPress = useLongPress(
    useCallback(
      (oid: number) => {
        if (findCard(state, oid) !== null) setHeldCard(oid);
      },
      [state],
    ),
  );

  return { heldCard, setHeldCard, closeHold, readHovered, longPress };
}
