/**
 * Shared motion presets.
 *
 * One place for every spring in the app, so the whole table feels like it obeys
 * the same physics. Components import a preset; they never inline a transition.
 */

import type { Transition } from "motion/react";

/** Cards settling into a slot: quick, barely overshoots. */
export const settle: Transition = {
  type: "spring",
  stiffness: 420,
  damping: 34,
  mass: 0.9,
};

/** Hand hover lift and drag snap-back: looser, visibly elastic. */
export const bouncy: Transition = {
  type: "spring",
  stiffness: 520,
  damping: 22,
  mass: 0.7,
};

/** Long zone-to-zone flights: slower so the eye can follow the card. */
export const flight: Transition = {
  type: "spring",
  stiffness: 190,
  damping: 26,
  mass: 1.1,
};

/** Tapping: a mechanical quarter-turn, not a wobble. */
export const mechanical: Transition = {
  type: "spring",
  stiffness: 300,
  damping: 30,
};

/** Panels, banners, dialogs. */
export const ease: Transition = { duration: 0.22, ease: [0.22, 1, 0.36, 1] };

export const quick: Transition = { duration: 0.12, ease: "easeOut" };
