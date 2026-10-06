/**
 * One screen's worth of arriving and leaving.
 *
 * Every route renders exactly one of these, which is what makes the outer
 * `AnimatePresence mode="wait"` work: it needs a single keyed child to swap, and
 * a route that returned a bare fragment would give it nothing to animate. The
 * `key` belongs on the `<Screen>` at the call site, because only the caller
 * knows whether two states are the same screen or two different ones.
 */

import { motion, usePresence } from "motion/react";
import { forwardRef, type ReactNode, useEffect, useRef } from "react";
import { useCursorNav } from "../../input/useCursorNav";
import { SCREEN_VARIANTS, type ScreenVariant } from "../../motion/springs";
import { FocusRing } from "../game/FocusRing";

/**
 * How long a leaving screen stays mounted: `ease`'s 220ms, with a frame or two
 * of slack so the fade is seen to finish. A number rather than an animation's
 * word for "done" -- see the note in `Screen`.
 */
const EXIT_MS = 320;

interface Props {
  variant?: ScreenVariant;
  /** The one-line panels -- "Dealing…", "Finding the pod…" -- centre themselves. */
  center?: boolean;
  testId?: string;
  children: ReactNode;
}

/*
 * `forwardRef` for `GameRoute`'s `AnimatePresence mode="popLayout"`, which
 * measures the leaving screen through a ref to lift it out of the flow. Every
 * other caller ignores it.
 */
export const Screen = forwardRef<HTMLDivElement, Props>(function Screen(
  { variant = "slide", center = false, testId, children },
  ref,
) {
  /*
   * The controller lives here rather than on the board, and that is the whole
   * point of putting it here.
   *
   * Every route renders exactly one `Screen`, so this is the one place that
   * covers the front door, the pod lobby, the deck catalogue and the table
   * alike. Mounting it in `Table` -- which is where it started -- meant the
   * lobby had no ring and no stops at all: a controller could not create a pod,
   * pick a deck, or start a game, which is a more complete blocker than any of
   * the board work it was covering.
   *
   * `Table` still calls `useCursorResolve()` itself. React only runs layout
   * effects for components that re-render, and the board re-renders on every
   * engine push without this wrapper re-rendering -- see `FocusRing`.
   */
  const [present, safeToRemove] = usePresence();
  useCursorNav(present);

  /*
   * A SCREEN LEAVES ON A CLOCK, NOT ON AN ANIMATION.
   *
   * The outer `AnimatePresence mode="wait"` mounts the next screen only once
   * this one's exit has reported complete, and an opacity exit started while
   * the entrance was still in flight was measured never to (the opening hand
   * and the prompt dialog first; `docs/bugs.md`). Here the consequence is
   * worse than a stuck overlay: NOTHING mounts. Back to the front door and
   * forward again inside a quarter of a second -- which is what a history
   * gesture on a slow machine looks like -- left the door fading forever and
   * the table never arriving, a blank page with no error in it
   * (`e2e/pod.spec.ts`, "both browsers land on the table", on a CI runner).
   *
   * So the root carries no `exit`: while present it animates to its variant's
   * `animate`, while leaving to its `exit` look, and `safeToRemove` is called
   * by a timer the animation cannot hold up -- through a ref keyed on presence
   * alone, because `safeToRemove` is rebuilt on every render of the boundary.
   * A lost fade is a cut. It is never a blank screen.
   */
  const removeRef = useRef(safeToRemove);
  removeRef.current = safeToRemove;
  useEffect(() => {
    if (present) return;
    const timer = setTimeout(() => removeRef.current?.(), EXIT_MS);
    return () => clearTimeout(timer);
  }, [present]);
  const { initial, animate, exit, ...rest } = SCREEN_VARIANTS[variant];

  return (
    <motion.div
      ref={ref}
      className={center ? "screen screen--center" : "screen"}
      data-testid={testId}
      data-closing={present ? undefined : true}
      initial={initial}
      animate={present ? animate : exit}
      {...rest}
    >
      {children}
      {/*
        Only while present. Where two screens overlap -- `GameRoute`'s
        cross-fade -- a leaving screen's ring would be a second `#ring` in the
        document, and its unmount would reset the arriving screen's ring in the
        middle of placing it. A screen on its way out has nothing to point at:
        every stop in it is already filtered out by `data-closing`.
      */}
      {present && <FocusRing context={testId ?? variant} />}
    </motion.div>
  );
});
