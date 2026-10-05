/**
 * The right stick is a scroll wheel for whatever the ring is on.
 *
 * The left stick is the cursor (it stands in for the d-pad in `pad.ts`), and
 * the right one was read every frame and then thrown away. A player holding a
 * card whose rules text ran past the reader had no way to see the rest, and a
 * long action list could only be read by walking the ring down it -- which
 * moves the thing you are about to press.
 *
 * WHICH BOX, and the rule is the two places a player is actually looking:
 *
 * - **On a card** (`card:<oid>`) it scrolls the reader, because the reader is
 *   showing that card and the text is what you want more of. Never the lane the
 *   card sits in: scrolling the board would carry the card you are pointing at
 *   out from under the ring.
 * - **On anything else** it scrolls the nearest box around the ring that has
 *   something to scroll -- the action panel's list, a combobox's rows. The ring
 *   stays on its stop and is told to follow it as the box moves.
 *
 * Nothing here is React state, for `cursor.ts`'s reason: a scroll every frame
 * must not re-render anything.
 */

import { useEffect } from "react";
import { getCursor, refollowCursor } from "./cursor";
import { onFrame as onPadFrame } from "./pad";
import { stopElement } from "./stops";

/** Pixels per second at full deflection. A full reader scrolls in about half a second. */
export const SCROLL_SPEED = 900;

/** A frame gap longer than this is a stall (a hidden tab), not a long push. */
const MAX_DT = 0.1;

/** Whether `el` scrolls vertically and has anything to scroll. */
export function scrollsY(el: Element): boolean {
  if (el.scrollHeight <= el.clientHeight + 1) return false;
  const overflow = getComputedStyle(el).overflowY;
  return overflow === "auto" || overflow === "scroll";
}

/** The reader's scroller, if what it is showing runs past its box. */
function readerScroller(doc: Document): HTMLElement | null {
  const reader = doc.querySelector<HTMLElement>('[data-testid="card-preview"]');
  if (!reader) return null;
  for (const el of reader.querySelectorAll<HTMLElement>("*")) {
    if (scrollsY(el)) return el;
  }
  return null;
}

/** The nearest ancestor of `el` that has something to scroll. */
function scrollerAround(el: HTMLElement): HTMLElement | null {
  for (let node = el.parentElement; node; node = node.parentElement) {
    if (node === node.ownerDocument.body) return null;
    if (scrollsY(node)) return node;
  }
  return null;
}

/** The box the right stick scrolls for the stop the ring is on. */
export function scrollTargetFor(
  stop: string | null,
  doc: Document = document,
): HTMLElement | null {
  if (stop === null) return null;
  if (stop.startsWith("card:")) return readerScroller(doc);
  const el = stopElement(stop);
  return el ? scrollerAround(el) : null;
}

/**
 * How far to scroll this frame for a dead-zoned stick reading.
 *
 * Squared, keeping the sign: a light push reads a line at a time and a full
 * one skims, which a linear map cannot do both of.
 */
export function scrollStep(y: number, dt: number): number {
  return y * Math.abs(y) * SCROLL_SPEED * Math.min(dt, MAX_DT);
}

/** Scroll the focused box while the right stick is pushed. Mount once per screen. */
export function useStickScroll(): void {
  useEffect(() => {
    let last: number | null = null;
    // Sub-pixel steps are dropped by `scrollTop`, so a gentle push would
    // never move at all; the remainder carries to the next frame instead.
    let carry = 0;
    const off = onPadFrame((frame) => {
      const y = frame.rstick.y;
      const now = performance.now();
      const dt = last === null ? 0 : (now - last) / 1000;
      last = y === 0 ? null : now;
      if (y === 0) {
        carry = 0;
        return;
      }
      const stop = getCursor();
      const box = scrollTargetFor(stop);
      if (!box) return;
      carry += scrollStep(y, dt);
      const whole = Math.trunc(carry);
      if (whole === 0) return;
      carry -= whole;
      box.scrollTop += whole;
      // The reader scrolling moves nothing the ring is on; a list scrolling
      // carries the ring's stop with it.
      if (!stop?.startsWith("card:")) refollowCursor();
    });
    return off;
  }, []);
}
