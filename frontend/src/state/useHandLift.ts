/**
 * The resolved value of `--hand-lift`, in pixels.
 *
 * The hovered hand card rises by this much, and `.hand__slot` is padded upward
 * by exactly the same amount so the pointer stays inside the slot for the whole
 * rise -- without that padding, raising a card takes its hit box out from under
 * the cursor, `mouseleave` fires, the card falls back under the cursor, and it
 * oscillates for as long as you rest near an edge. Two numbers that must agree,
 * one of which has to be in CSS: so CSS owns it and the motion value reads it.
 *
 * It differs between layouts -- 46px on a desktop, less on a handheld where the
 * hand sits directly under the hint bar -- which is exactly why it could not
 * stay a literal in `HandFan`.
 *
 * Modelled on `useCardBase`, and re-reading on resize for the same reason: the
 * value changes when the handheld breakpoint does, and that is a resize.
 */

import { useEffect, useState } from "react";

/** What `board.css` declares at `:root`. Also the jsdom answer. */
export const FALLBACK_HAND_LIFT = 46;

function readHandLift(): number {
  if (typeof window === "undefined" || typeof getComputedStyle !== "function") {
    return FALLBACK_HAND_LIFT;
  }
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--hand-lift");
  const parsed = Number.parseFloat(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : FALLBACK_HAND_LIFT;
}

export function useHandLift(): number {
  const [lift, setLift] = useState(readHandLift);

  useEffect(() => {
    const measure = () => setLift(readHandLift());
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  return lift;
}
