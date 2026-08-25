/**
 * The way out of an overlay, for every input at once and for one overlay at a
 * time.
 *
 * `buttons.ts` states the rule this implements: "`Escape`, `Backspace` and `B`
 * are now one thing: a strict unwind". The board and the front door honour it;
 * the lobby's three overlays did not. Each of them bound a bare `window`
 * keydown for `Escape` and nothing at all for the pad's `b`, which cost two
 * separate bugs.
 *
 * **B did nothing in the deck catalogue.** The catalogue draws a `B — Back`
 * hint in its own footer, and there was no listener behind it anywhere in the
 * app -- `tests/hintsBound.test.ts` only asks whether a button is bound
 * SOMEWHERE, so a hint on a surface that does not bind it passes. A player on a
 * pad pressed the advertised button, the game ignored it, and whatever their
 * controller layout does with an unclaimed B took over instead. On a Steam Deck
 * that is a history step, and from `/pods/{code}` a history step is the front
 * door -- so Back out of a modal dropped them out of the pod.
 *
 * **And Escape closed two overlays at once.** The catalogue can open a dossier
 * over itself. Both listeners are on `window`, so one Escape ran both: the
 * dossier closed, and the catalogue underneath it -- which the player had not
 * asked to leave and could not see past the dossier -- closed with it. Backing
 * out of the top thing is the whole meaning of Back, and it has to back out of
 * exactly one.
 *
 * So the guard is `stopRoot()`: the ring already answers "which surface is on
 * top" for navigation, and this asks it the same question rather than inventing
 * a second stack that could disagree with the first. An overlay whose element
 * is not the current stop root has something over it and is not what Back
 * means.
 *
 * The pad's `b` is the primary channel, because `Escape` already arrives as one
 * -- and the raw key is answered only for the presses the pad layer will not
 * deliver, which is Escape typed into a text field. Answering both
 * unconditionally is the other way to close two overlays on one press: the
 * keydown takes the dossier, and the `b` a frame later finds the catalogue
 * beneath it on top and takes that too.
 */

import { type RefObject, useEffect } from "react";
import { on, padTakesKey, startPad } from "./pad";
import { stopRoot } from "./stops";

/**
 * Close this overlay on Escape or B, but only while it is the topmost one.
 *
 * `ref` goes on the element carrying `data-modal-root` -- the same node
 * `stopRoot` picks out -- so there is one answer to "is this the top" rather
 * than one per dialog.
 */
export function useDismiss(ref: RefObject<HTMLElement | null>, onClose: () => void): void {
  useEffect(() => {
    // `Screen` starts the loop for the whole app; a dialog rendered on its own
    // -- a story, a component test -- would otherwise have no `b` at all, and
    // the exit a dialog owes cannot depend on who mounted it.
    startPad();
    const mine = () => ref.current !== null && stopRoot() === ref.current;

    /*
     * The presses the pad layer will NOT deliver, and only those.
     *
     * Escape typed into the deck search box is the case: a text field keeps
     * every non-direction key, so no `b` is emitted and the handler below never
     * runs. Answering the raw key unconditionally instead is what closed two
     * overlays on one press -- the keydown closed the dossier, and the `b` a
     * frame later found the catalogue underneath it on top and closed that too.
     */
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || padTakesKey(event)) return;
      if (mine()) onClose();
    };
    window.addEventListener("keydown", onKey);
    const offB = on("b", () => {
      if (mine()) onClose();
    });

    return () => {
      window.removeEventListener("keydown", onKey);
      offB();
    };
  }, [ref, onClose]);
}
