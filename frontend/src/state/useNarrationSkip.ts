/**
 * "Enough": skip the narration and put every moving thing back at rest.
 *
 * Two callbacks `Table` hands to everything that takes input. `skipAll` empties
 * the beat queue and stops the particles, the card actuators and the shake,
 * which all run on their own clocks past the beat that started them.
 * `gateInput` is the rule every gesture goes through first: a press during
 * narration means "get on with it" AND the thing that was pressed, so it skips
 * and then reports only whether a genuine request is in flight. Moved out of
 * `Table.tsx` as they were.
 */

import { useCallback } from "react";
import { clearParticles } from "../components/game/ParticleLayer";
import { restAll } from "../fx/actuators";
import type { useGame } from "./useGame";

type Narration = ReturnType<typeof useGame>["narration"];

export function useNarrationSkip(narration: Narration, busy: boolean) {
  /**
   * Empty the queue and put the board back at rest.
   *
   * Skipping used to leave whatever was mid-flight still flying: `narration`
   * owns the beats, but the particles, the card actuators and the screen shake
   * all run on their own clocks past the end of the beat that started them --
   * which is exactly what makes a turn read as continuous, and exactly what you
   * do not want the instant the player says "enough".
   */
  const skipNarration = narration.skip;
  const skipAll = useCallback(() => {
    skipNarration();
    clearParticles();
    restAll();
  }, [skipNarration]);

  /**
   * Whether this gesture should be dropped, and the side effect of not dropping it.
   *
   * A click while narration is playing means "get on with it" -- *and* it means
   * the thing that was clicked. It used to mean only the first: the queue was
   * skipped and the gesture thrown away, so for the second or two after every
   * action the board ignored you, and playing it felt like it needed spamming.
   * Only a genuine in-flight request gates input now.
   */
  const narrationBusy = narration.busy;
  const gateInput = useCallback(() => {
    if (narrationBusy) skipAll();
    return busy;
  }, [busy, narrationBusy, skipAll]);

  return { skipAll, gateInput };
}
