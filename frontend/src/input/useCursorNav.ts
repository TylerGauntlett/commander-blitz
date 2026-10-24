/**
 * The half of controller navigation that is the same on every screen.
 *
 * Directions move the ring, the pointer snaps it, and the pad and input-mode
 * watchers get started. What each *button* means is not here -- that is the
 * screen's business, and `Table` binds A/B/X/Y against its own decision state.
 *
 * Mounted by the board and by each lobby screen, so the lobby is pad-playable
 * for free rather than as a second implementation.
 */

import { useEffect, useRef } from "react";
import { play } from "../audio/sfx";
import { useUiStore } from "../state/uiStore";
import { getCursor, moveCursor, setCursor } from "./cursor";
import { getInputMode, isPointerMode, startInputMode } from "./inputMode";
import { on, rumble, startPad } from "./pad";
import { ringPress } from "./ring";
import { stopAtPoint, stopElement } from "./stops";

/** Directions, and the sound each outcome makes. */
const DIRECTIONS = ["up", "down", "left", "right"] as const;

export function useCursorNav(active = true): void {
  /*
   * ONE SCREEN ANSWERS THE PAD, EVEN WHILE TWO ARE MOUNTED.
   *
   * `Screen` passes its presence. Behind `App`'s `mode="wait"` a leaving screen
   * is alone and this changes nothing, but `GameRoute` cross-fades the deal
   * into the table, and for that overlap both screens have this hook bound --
   * so one `A` would have clicked the ring's element twice (a toggle that
   * undoes itself) and one direction would have moved it two stops. A ref
   * rather than a dependency, so the bindings are not torn down and re-made
   * on the way out.
   */
  const live = useRef(active);
  live.current = active;

  useEffect(() => {
    startInputMode();
    startPad();

    const muted = () => useUiStore.getState().muted;

    /*
     * `A` IS A CLICK.
     *
     * Not "A does what a click does" -- it dispatches the click, on the element
     * the ring is on. That is the whole implementation, and it is the reason
     * the controller cannot drift from the mouse: there is no second routing
     * table to keep in step, no branch per stop kind, and no way for a pad to
     * reach an action a pointer cannot. It is the same argument `actionAttrs`
     * makes for stop ids, one level up.
     *
     * It replaced a hand-written `confirm()` that resolved the stop back to a
     * card or a seat and called the matching handler. That version worked on
     * the board and did nothing at all everywhere else -- so a controller could
     * navigate the front door and the pod lobby but not press anything on
     * either, which meant it could not start a game.
     */
    const press = on("a", () => {
      if (!live.current) return;
      const stop = getCursor();
      if (!stop) return;
      const el = stopElement(stop);
      if (!el) return;
      // The squeeze goes first: `click` may replace this element outright, and
      // an impulse written after that would be written to nothing.
      ringPress();
      el.click();
    });

    const unbind = DIRECTIONS.map((dir) =>
      on(dir, () => {
        if (!live.current) return;
        /*
         * A CONTAINER MAY OWN AN AXIS.
         *
         * `pad.ts:on` lets every listener for a button fire and gives none of
         * them a way to say "handled" -- so a component that wanted Left and
         * Right for itself (a long list that pages on them) would get them AND
         * the ring would move, or be denied, for the same press. The same
         * reasoning that makes `A` a click makes this a DOM event: the element
         * under the ring says `data-nav-x`, and the press becomes a `padnav`
         * event on it that the component handles as it would a click. The
         * ring is not moved and nothing is denied; the component says what
         * happened. Only the horizontal axis so far, because that is the one
         * a vertical list has nothing else to do with.
         */
        if (dir === "left" || dir === "right") {
          const stop = getCursor();
          const owner = stop ? stopElement(stop)?.closest<HTMLElement>("[data-nav-x]") : null;
          if (owner) {
            owner.dispatchEvent(new CustomEvent("padnav", { detail: dir, bubbles: true }));
            if (!muted()) play("move");
            return;
          }
        }
        const moved = moveCursor(dir);
        if (moved) {
          if (!muted()) play("move");
          return;
        }
        /*
         * A wall, said three ways.
         *
         * `moveCursor` has already nudged the ring into it, which is the
         * channel that always works. The other two are deliberately redundant:
         * a handheld is routinely played muted, and `vibrationActuator` does
         * not exist in Firefox on the Deck's desktop mode at all. No fact in
         * this app may depend on haptics alone.
         */
        if (!muted()) play("deny");
        rumble(55, 0.22);
      }),
    );

    return () => {
      press();
      for (const off of unbind) off();
    };
  }, []);

  /*
   * The pointer, which on a Deck is the trackpads and the touchscreen.
   *
   * Steam Input presents both as ordinary mouse events, so this one path covers
   * finger, trackpad and mouse -- and it is the reason the ring has to be
   * reachable by pointing as well as by walking. Snapping (rather than tracking
   * freely) is what makes a trackpad usable: `SNAP` catches the nearest stop and
   * nothing else moves the ring.
   *
   * Guarded on the mode so that an ordinary desktop mouse user, who has no ring
   * at all, does not pay for a `getBoundingClientRect` sweep per click.
   */
  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (!live.current || isPointerMode(getInputMode())) return;
      const stop = stopAtPoint(event.clientX, event.clientY);
      if (stop) setCursor(stop);
    };
    window.addEventListener("pointerdown", onPointerDown, { passive: true });
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, []);
}
