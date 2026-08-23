/**
 * One screen's worth of arriving and leaving.
 *
 * Every route renders exactly one of these, which is what makes the outer
 * `AnimatePresence mode="wait"` work: it needs a single keyed child to swap, and
 * a route that returned a bare fragment would give it nothing to animate. The
 * `key` belongs on the `<Screen>` at the call site, because only the caller
 * knows whether two states are the same screen or two different ones.
 */

import { motion } from "motion/react";
import type { ReactNode } from "react";
import { useCursorNav } from "../../input/useCursorNav";
import { SCREEN_VARIANTS, type ScreenVariant } from "../../motion/springs";
import { FocusRing } from "../game/FocusRing";

interface Props {
  variant?: ScreenVariant;
  /** The one-line panels -- "Dealing…", "Finding the pod…" -- centre themselves. */
  center?: boolean;
  testId?: string;
  children: ReactNode;
}

export function Screen({ variant = "slide", center = false, testId, children }: Props) {
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
  useCursorNav();

  return (
    <motion.div
      className={center ? "screen screen--center" : "screen"}
      data-testid={testId}
      {...SCREEN_VARIANTS[variant]}
    >
      {children}
      <FocusRing context={testId ?? variant} />
    </motion.div>
  );
}
