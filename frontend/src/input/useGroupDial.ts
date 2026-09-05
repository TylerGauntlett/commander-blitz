/**
 * The region dial's hold: `L2` past the analog threshold for 260ms opens it,
 * the release closes it whether or not it ever opened.
 *
 * Lifted out of `Table.tsx` as it was. The state is local rather than in
 * `uiStore` for the reason the `R2` reading hold is: a hold has no meaning
 * across a re-render, and a hold kept in a store is a hold that can get stuck.
 */

import { useEffect, useRef, useState } from "react";
import { onFrame as onPadFrame } from "./pad";

export function useGroupDial(): [boolean, (open: boolean) => void] {
  const [dialOpen, setDialOpen] = useState(false);

  /*
   * The dial, on `L2` HELD.
   *
   * Not on a hold of `L1`, which is where this started and could not work:
   * `pad.ts` reports PRESSES and has no release event for a shoulder, so a
   * "hold" there is a timer with nothing to cancel it -- a tap would open the
   * dial 260ms later, having already stepped.
   *
   * `L2` is a TRIGGER, and `onFrame` reports its analog position every frame.
   * That is the same channel the `R2` opponent reader is held on, for the same
   * stated reason: letting go is not something you can forget to do. 0.5 is
   * past any resting value and well short of the click.
   *
   * A TAP MUST NOT FLASH IT, and "the tap is over before the dial is worth
   * looking at" was not true enough to rely on.
   *
   * Opening on the press edge meant a tap -- which is a good 100ms of trigger,
   * because that is how long a thumb takes -- mounted the dial and unmounted it
   * again. Two things came out of those two frames, and only the first was
   * cosmetic: a visible flicker across the middle of the screen, and a ring
   * that moves twice. `GroupDial` puts the ring on its own landing spoke as it
   * opens, and closing an overlay hands the ring back to the stop that was
   * underneath -- which is a `resolveCursor` that lands AFTER the tap has
   * finished. Any direction pressed inside that window is overwritten by the
   * restore, so `L2` then right -- jump to the combat bar, step to the slab,
   * which is the whole gesture `L2` exists for -- ate the second press about
   * half the time. From the player's side the pad simply missed inputs.
   *
   * So the dial waits. `HOLD` is the same 260ms the shoulder taps were timed
   * against, and unlike those this one has something to cancel it: a trigger is
   * analog, `onFrame` reports its position every frame, and the release edge is
   * a real event. A tap starts the timer and clears it; a hold lets it fire.
   */
  const HOLD = 260;
  const l2Held = useRef(false);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const off = onPadFrame((frame) => {
      const held = frame.l2 > 0.5;
      /*
       * ON THE TRIGGER'S EDGE, NOT ON ITS LEVEL.
       *
       * This wrote `dialOpen = held` every frame, which is correct while `L2` is
       * the only thing that opens the dial and wrong the moment anything else
       * does: the button in the foot would set it true, the very next frame
       * would read a resting trigger and set it straight back to false, and the
       * dial would appear not to open at all. A press and a release are events;
       * a trigger at rest is not one.
       */
      if (held === l2Held.current) return;
      l2Held.current = held;
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
      if (held) timer = setTimeout(() => setDialOpen(true), HOLD);
      // The release closes it whether or not it ever opened, so a hold that is
      // let go of never leaves the dial up.
      else setDialOpen(false);
    });
    return () => {
      if (timer !== null) clearTimeout(timer);
      off();
    };
  }, []);

  return [dialOpen, setDialOpen];
}
