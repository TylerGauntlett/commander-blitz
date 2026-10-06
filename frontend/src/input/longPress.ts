/**
 * A long-press reads the card under the finger.
 *
 * A touch screen has no hover, so the preview rail -- "point at a card to read
 * it" -- was unreachable on a phone, and a tap on a hand card PLAYS it. That
 * left no way to read a card before committing to it. The desktop reads with a
 * right-click and the Deck with `Y`; both open the full card view (`CardHold`).
 * This is the phone's way into the same view: hold a finger still on anything
 * that carries a card for `HOLD_MS` and it opens.
 *
 * Touch and pen only. A mouse already has hover and a right-click, and a mouse
 * button held down is the start of a drag rather than a request to read.
 *
 * THE TAP THAT ENDS THE HOLD IS SWALLOWED. Lifting the finger after the view
 * opens still delivers a `click` to the card underneath, and on a hand card a
 * click is "play this" -- so the press that read a card would also cast it.
 * One capture-phase listener eats the next click after a hold fires.
 */

import { type PointerEvent as ReactPointerEvent, useCallback, useEffect, useRef } from "react";

/** How long a finger has to stay put. iOS's own long-press is about 500ms. */
export const HOLD_MS = 450;

/** How far it may drift and still be a hold rather than a scroll. */
export const HOLD_SLOP = 10;

/**
 * The card an element stands for, if any.
 *
 * `data-preview-oid` first: it is what a commander plinth, an action row or an
 * opponent's seat says it would show in the preview, and those are not cards
 * themselves. Then the nearest `data-oid`, which every rendered card carries.
 */
export function oidAt(target: EventTarget | null): number | null {
  if (!(target instanceof Element)) return null;
  const host = target.closest("[data-preview-oid], [data-oid]");
  if (!host) return null;
  const raw = host.getAttribute("data-preview-oid") ?? host.getAttribute("data-oid");
  const oid = Number(raw);
  return raw !== null && raw !== "" && Number.isFinite(oid) ? oid : null;
}

export function useLongPress(onHold: (oid: number) => void) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const origin = useRef<{ x: number; y: number } | null>(null);

  const cancel = useCallback(() => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
    origin.current = null;
  }, []);

  useEffect(() => cancel, [cancel]);

  const onPointerDown = useCallback(
    (event: ReactPointerEvent) => {
      if (event.pointerType === "mouse") return;
      const oid = oidAt(event.target);
      if (oid === null) return;
      cancel();
      origin.current = { x: event.clientX, y: event.clientY };
      timer.current = setTimeout(() => {
        timer.current = null;
        origin.current = null;
        // Eat the click the finger's lift is about to deliver. Once, and only
        // if it comes promptly -- a stale listener would swallow a later,
        // deliberate tap.
        const swallow = (click: MouseEvent) => {
          click.stopPropagation();
          click.preventDefault();
        };
        window.addEventListener("click", swallow, { capture: true, once: true });
        setTimeout(() => window.removeEventListener("click", swallow, { capture: true }), 800);
        onHold(oid);
      }, HOLD_MS);
    },
    [cancel, onHold],
  );

  const onPointerMove = useCallback(
    (event: ReactPointerEvent) => {
      const start = origin.current;
      if (!start) return;
      if (Math.hypot(event.clientX - start.x, event.clientY - start.y) > HOLD_SLOP) cancel();
    },
    [cancel],
  );

  return {
    onPointerDown,
    onPointerMove,
    onPointerUp: cancel,
    onPointerCancel: cancel,
  };
}
