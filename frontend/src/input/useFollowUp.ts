/**
 * Following a decision: the ring goes to the second half of a two-press move.
 *
 * Lifted out of `Table.tsx` as two hooks rather than one, because the ORDER of
 * the two halves inside `Table` is the point. `useFollowUp` has to run before
 * the routing callbacks that call `followUp`; `useFollowThrough`'s layout
 * effect has to run after `useCursorResolve()`, or a resolve running afterwards
 * would put the ring back.
 */

import {
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import type { GameView, LegalAction } from "../api/types";
import { followUpStops, type Gesture } from "../logic/followUp";
import { setCursor } from "./cursor";
import { getGroup, setGroup } from "./groups";
import { sendableIn, stopRoot } from "./stops";

export function useFollowUp() {
  /**
   * The gesture whose second half the ring has not been moved to yet.
   *
   * Declared here rather than beside its effect because the routing callbacks
   * below close over `followUp` AND name it in their dependency arrays, and a
   * dependency array is evaluated where it is written -- a `const` declared
   * further down would be in its temporal dead zone at that moment. The effect
   * that drains this sits after `useCursorResolve()`, which is the ordering
   * that matters: a resolve running afterwards would put the ring back.
   */
  const [follow, setFollow] = useState<Gesture | null>(null);
  const followAt = useRef<LegalAction[] | null>(null);
  const followUp = useCallback((gesture: Gesture) => {
    followAt.current = null;
    setFollow(gesture);
  }, []);
  return { follow, setFollow, followAt, followUp };
}

interface FollowThrough {
  follow: Gesture | null;
  setFollow: Dispatch<SetStateAction<Gesture | null>>;
  followAt: MutableRefObject<LegalAction[] | null>;
  actions: LegalAction[];
  state: GameView;
  stagedBlocks: Record<number, number>;
}

export function useFollowThrough({
  follow,
  setFollow,
  followAt,
  actions,
  state,
  stagedBlocks,
}: FollowThrough) {
  /* --------------------------------------------------- following a decision
   *
   * HALF THE DECISIONS IN THIS GAME ARE TWO PRESSES, AND NOTHING MOVED BETWEEN
   * THEM. Press an instant in your hand and the board lights up with legal
   * targets while the ring is still on the card in your hand; press one of your
   * creatures during a block declaration and the attacker it has to be pointed
   * at is on an opponent's board, which at 1280x800 is a lane clipped to zero
   * height and therefore not a stop at all. A pointer never pays either cost,
   * because a pointer arrives at the second half of a decision by moving there.
   *
   * `logic/followUp.ts` answers WHERE, as an ordered list, and this is the
   * whole of the DOM half. Two things it has to get right:
   *
   * - **The group is released before the cursor moves.** `setCursor` resolves
   *   through `activeRoot()`, which is still the region being left, so a target
   *   outside it is not findable and the ring silently does not move. Exactly
   *   the bug `cursor.ts:moveCursor` records; the region is put back if nothing
   *   in the list lands, and the cursor->group reconciler below sets the right
   *   one when something does.
   * - **A candidate has to be LANDABLE, not merely present.** `setCursor` asks
   *   `stopElement`, which asks the DOM for the id and nothing else -- so it
   *   accepts an opponent's attacker sitting in a lane clipped to zero height,
   *   which is precisely the stop this whole module exists to route around. It
   *   took the ring straight back to the dead end it was avoiding.
   *
   *   `sendableIn` and not `candidatesIn`, and the difference is the whole
   *   fallback. Stepping does not scroll, so `onScreen` rightly refuses a row
   *   past the fold of the action list; a JUMP does scroll, because `stamp`
   *   calls `keepInView`. Filtering by the stepping rule rejected the panel row
   *   for any blocker below the fold -- which is precisely the row the fallback
   *   exists to reach -- and the ring stayed on the creature with nothing to do.
   * - **A gesture that asks the server waits for its answer.** The three combat
   *   gestures stage into `uiStore` and are true the moment they are made.
   *   Playing a card is a mutation, and running against the pre-mutation action
   *   list would send the ring to a card the land drop has just made
   *   unplayable. So that one holds until `actions` is a different array.
   */
  useLayoutEffect(() => {
    if (!follow) return;
    if (follow.kind === "played-from-hand") {
      if (followAt.current === null) {
        followAt.current = actions;
        return;
      }
      if (followAt.current === actions) return;
    }
    const candidates = followUpStops(state, actions, follow, stagedBlocks);
    setFollow(null);
    if (candidates.length === 0) return;
    const was = getGroup();
    setGroup(null);
    const sendable = sendableIn(stopRoot());
    for (const id of candidates) {
      if (sendable.has(id) && setCursor(id)) return;
    }
    setGroup(was);
  }, [follow, actions, state, stagedBlocks, setFollow, followAt]);
}
