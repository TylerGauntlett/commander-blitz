/**
 * The resolved value of `--card-w-base`, in pixels.
 *
 * Almost every zone expresses its size as a CSS `calc()` against that variable
 * and never needs this. The hand is the exception: it positions its slots
 * absolutely, so the fan's arithmetic genuinely needs a number, and a number
 * cannot be read out of a `clamp()` without asking the browser.
 *
 * Falls back to the old fixed width when there is no layout engine to ask --
 * jsdom returns "" for a custom property it never resolved -- so component
 * tests keep the geometry they were written against.
 */

import { useEffect, useState } from "react";
import { FALLBACK_BASE } from "../logic/cardSize";

function readCardBase(): number {
  if (typeof window === "undefined" || typeof getComputedStyle !== "function") {
    return FALLBACK_BASE;
  }
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--card-w-base");
  const parsed = Number.parseFloat(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : FALLBACK_BASE;
}

export function useCardBase(): number {
  const [base, setBase] = useState(readCardBase);

  useEffect(() => {
    // `--card-w-base` is keyed off viewport *height*, which is the binding
    // constraint on this board -- three lanes plus a hand is a vertical
    // problem, not a horizontal one. So this must listen to resize, not just
    // run once.
    const measure = () => setBase(readCardBase());
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  return base;
}
