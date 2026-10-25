/**
 * Which controls to draw, said out loud.
 *
 * `input/inputMode.ts` works it out on its own in every ordinary case, and this
 * exists for the case it cannot: **a Steam Deck in gaming mode is a controller
 * that arrives as a keyboard**. Steam Input grabs the pad, publishes no gamepad,
 * and sends arrow keys and Enter instead -- so every signal the app has says
 * "keyboard", and the hint bar tells somebody holding a controller to press
 * Enter and Esc. The heuristic catches the common shape of that; a preference
 * catches the rest, and is the only thing that cannot be wrong.
 *
 * Native `<button>`s, so on the front door `input/stops.ts` picks them up as
 * stops with no registration and the picker is reachable by the very controller
 * it is there to fix. That is not a detail: a control-scheme setting you can
 * only reach with a working control scheme is furniture.
 *
 * BUT ONLY ON A SURFACE THAT DECLARES NOTHING. `stopsIn` takes a surface that
 * declares even one `data-stop` at its word and gives it no fallback, and the
 * board's settings menu is one -- so there the four buttons were unreachable
 * (TECH_DEBT FB-12) while this comment said otherwise. `stops` gives them
 * declared ids for that host. It is a prop rather than always-on because the
 * opposite holds on the door: one declared stop there would switch the
 * fallback off for every other control on the screen.
 *
 * It subscribes, because unlike a `Glyph` this is one small component that has
 * to redraw when the mode resolves differently -- including when the heuristic
 * changes its mind under `auto`.
 */

import { useSyncExternalStore } from "react";
import {
  getInputMode,
  getScheme,
  type SchemePref,
  setScheme,
  subscribeInputMode,
} from "../../input/inputMode";
import { stopId } from "../../input/stops";

/**
 * The five, in the order a confused player reads them.
 *
 * `auto` first because it is the default and the right answer nearly always.
 * `pad` second because somebody who opened this screen is overwhelmingly likely
 * to be holding a controller the app has failed to notice -- that is what the
 * screen is for.
 */
const OPTIONS: { id: SchemePref; label: string; hint: string }[] = [
  { id: "auto", label: "Auto", hint: "Work it out from what you last used" },
  { id: "pad", label: "Gamepad", hint: "Always show A, B, X and Y" },
  { id: "keyboard", label: "Keyboard", hint: "Always show Enter, Esc and the arrows" },
  { id: "mouse", label: "Mouse", hint: "No button hints at all" },
  { id: "touch", label: "Touch", hint: "Tap to act, press and hold to read a card" },
];

interface Props {
  /** Declare `tool:scheme-<id>` stops, for a host that declares its own. */
  stops?: boolean;
}

export function SchemePicker({ stops = false }: Props = {}) {
  // Both are module state; this is the supported way to read a value React does
  // not own without tearing during a concurrent render.
  const scheme = useSyncExternalStore(
    subscribeInputMode,
    getScheme,
    () => "auto" as SchemePref,
  );
  const mode = useSyncExternalStore(subscribeInputMode, getInputMode, () => "mouse" as const);

  return (
    <div className="scheme">
      <div className="scheme__row" role="radiogroup" aria-label="Control scheme">
        {OPTIONS.map((option) => (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={scheme === option.id}
            className={scheme === option.id ? "scheme__opt scheme__opt--on" : "scheme__opt"}
            onClick={() => setScheme(option.id)}
            data-stop={stops ? stopId.tool(`scheme-${option.id}`) : undefined}
            data-testid={`scheme-${option.id}`}
            data-hint={option.hint}
          >
            {option.label}
          </button>
        ))}
      </div>
      {/*
        What `auto` actually decided, which is the only way to tell "the
        heuristic agrees with me" from "the heuristic has not noticed yet". A
        player whose Deck shows `Keyboard` here is looking at the bug, named.
      */}
      <p className="scheme__now">
        Currently showing <b>{mode === "pad" ? "gamepad" : mode}</b> controls.
      </p>
    </div>
  );
}
