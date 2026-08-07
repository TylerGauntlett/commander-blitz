/**
 * Playing the beat queue.
 *
 * `logic/events.ts` turns a batch of server events into timed beats; this runs
 * them. While the queue is draining the board is "busy": input is gated so a
 * click cannot land in the middle of an animation, and Skip empties it.
 *
 * The queue is a single piece of state and the head of it *is* the current
 * beat. Keeping a separate `current` alongside a queue ref was two sources of
 * truth for one thing, and needed an extra effect to keep them agreeing.
 *
 * The FX layer keeps its own short-lived list of the beats it has been shown,
 * so a damage numeral can still be floating while the next beat starts -- which
 * is what makes a combat step read as one motion rather than a slideshow.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { Beat } from "../logic/events";
import { SPEED_MULTIPLIER, type Speed } from "./uiStore";

export interface LiveBeat extends Beat {
  /** Unique across the whole session; `Beat.id` only sorts within one batch. */
  uid: number;
}

export interface Narration {
  /** The beat playing right now, or null when idle. */
  current: LiveBeat | null;
  /** How many beats are still waiting behind it. */
  queued: number;
  /** True while anything is playing: the board gates input on this. */
  busy: boolean;
  push: (beats: Beat[]) => void;
  skip: () => void;
  reset: () => void;
}

export function useNarration(speed: Speed): Narration {
  const [queue, setQueue] = useState<LiveBeat[]>([]);
  const nextUid = useRef(1);

  /**
   * "Instant" means no narration, not narration with a zero hold.
   *
   * Even a 0ms timer costs a React tick per beat, so a two-hundred-event batch
   * still held the board busy -- and therefore uninteractable -- for hundreds
   * of milliseconds, with the buttons flickering between enabled and disabled
   * the whole time. Dropping the beats on the floor is what the setting means.
   */
  const instant = speed === "instant";
  const current = !instant && queue.length > 0 ? queue[0] : null;

  const push = useCallback(
    (beats: Beat[]) => {
      if (instant || beats.length === 0) return;
      // Uids are assigned here rather than inside the updater: updaters must
      // stay pure, and StrictMode runs them twice.
      const live = beats.map((beat) => ({ ...beat, uid: nextUid.current++ }));
      setQueue((current_) => [...current_, ...live]);
    },
    [instant],
  );

  const skip = useCallback(() => setQueue([]), []);

  // Switching to instant mid-game drops whatever was still queued.
  useEffect(() => {
    if (instant) setQueue((rest) => (rest.length === 0 ? rest : []));
  }, [instant]);

  useEffect(() => {
    if (current === null) return;
    const ms = Math.max(0, current.hold / SPEED_MULTIPLIER[speed]);
    const timer = setTimeout(() => setQueue((rest) => rest.slice(1)), ms);
    return () => clearTimeout(timer);
  }, [current, speed]);

  return {
    current,
    queued: instant ? 0 : Math.max(0, queue.length - 1),
    busy: !instant && queue.length > 0,
    push,
    skip,
    reset: skip,
  };
}
