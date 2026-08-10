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
import { SCREEN_VARIANTS, type ScreenVariant } from "../../motion/springs";

interface Props {
  variant?: ScreenVariant;
  /** The one-line panels -- "Dealing…", "Finding the pod…" -- centre themselves. */
  center?: boolean;
  testId?: string;
  children: ReactNode;
}

export function Screen({ variant = "slide", center = false, testId, children }: Props) {
  return (
    <motion.div
      className={center ? "screen screen--center" : "screen"}
      data-testid={testId}
      {...SCREEN_VARIANTS[variant]}
    >
      {children}
    </motion.div>
  );
}
