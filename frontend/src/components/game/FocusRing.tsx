/**
 * The ring's two boxes, and the two mechanisms that keep it pointing at reality.
 *
 * This component renders almost nothing -- `#ring` and `#ringtrail`, both empty
 * and both driven imperatively by `input/ring.ts`. What it is really for is the
 * lifecycle: being mounted inside a surface means its layout effect fires after
 * that surface commits, which is how the cursor re-derives itself.
 *
 * ## Why a layout effect with no dependency array
 *
 * `Table` re-renders on every engine push, and each of those replaces the node
 * the ring was sitting on. A layout effect with no deps runs after *every*
 * commit of its parent, before the browser paints -- so the cursor is resolved
 * against the new markup in the same frame the markup appeared in. Anything
 * later (an effect, a rAF) shows one frame of a ring in the wrong place.
 *
 * This is the fix for the worst bug the design round found: walk the ring onto
 * the commit slab, press it, the slab rebuilds, the ring goes out -- and it can
 * never come back, because navigation starts from `[data-cursor]` and there is
 * no longer one.
 *
 * ## Why a MutationObserver as well
 *
 * The layout effect only sees commits of *this component's parent*. Two things
 * replace DOM outside that: `AnimatePresence` exits, which unmount on their own
 * clock, and framer `layoutId` swaps, which move a node between mount points.
 * Either can delete the element wearing `data-cursor` without this component
 * re-rendering at all. The observer is the backstop, coalesced to a microtask so
 * a wrath removing six permanents costs one re-resolve rather than six.
 */

import { useEffect, useLayoutEffect } from "react";
import { resolveCursor, restampCursor, setCursorContext } from "../../input/cursor";
import { resetRing, setRingProfile } from "../../input/ring";
import { useUiStore } from "../../state/uiStore";

interface Props {
  /**
   * The screen and overlay the ring is on.
   *
   * A change means teleport rather than fly: a spring across a screen change is
   * a spring across nothing, because the two endpoints were never on screen
   * together. See `retargetRing`.
   */
  context: string;
}

/**
 * Re-derive the cursor after this component's own commit.
 *
 * A hook rather than part of `FocusRing`, because the two have to be mounted in
 * different places and the reason is subtle: React only runs a component's
 * layout effects when *that component* re-renders. `FocusRing` lives in
 * `Screen`, which is every route's single wrapper -- but `Table` re-renders on
 * every engine push without `Screen` re-rendering at all, so a resolve owned by
 * the ring would never fire for the surface that changes most.
 *
 * So the surface that owns the markup calls this, and the ring only draws.
 * `resolveCursor` is idempotent, so both calling it is harmless.
 */
export function useCursorResolve(): void {
  // No dependency array: after every commit of whatever surface calls it.
  useLayoutEffect(() => {
    resolveCursor();
  });
}

export function FocusRing({ context }: Props) {
  const speed = useUiStore((s) => s.speed);

  // Before the resolve below, so the first flight of a new context uses the
  // right profile rather than the previous screen's.
  setCursorContext(context);
  setRingProfile(speed === "instant" ? "swift" : "full");

  useCursorResolve();

  useEffect(() => {
    const root = document.querySelector(".table") ?? document.querySelector(".screen");
    if (!root || typeof MutationObserver === "undefined") return;
    let queued = false;
    const observer = new MutationObserver(() => {
      if (queued) return;
      queued = true;
      queueMicrotask(() => {
        queued = false;
        restampCursor();
      });
    });
    observer.observe(root, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  // The ring is a singleton driven by module state, so a remount -- a new game,
  // a story re-rendering -- has to put it back at rest rather than springing
  // from wherever the last screen left it.
  useEffect(() => resetRing, []);

  return (
    <>
      {/*
        Rendered unconditionally and positioned by the spring. `aria-hidden`
        because the ring is a picture of where focus is, and focus itself is
        already on the element -- `cursor.ts` calls `.focus()` so assistive tech
        follows the same object. Announcing both would say everything twice.
      */}
      <div id="ringtrail" aria-hidden="true" />
      <div id="ring" aria-hidden="true" data-testid="focus-ring" />
    </>
  );
}
