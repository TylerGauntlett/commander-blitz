/**
 * Why your controller is not working, said in the app rather than in a console.
 *
 * `input/pad.ts:padDiagnostics` has computed exactly the right three facts since
 * it was written -- `supported`, `secure`, `focused` -- and its own docstring
 * says why: those separate an app problem from an environment one, all three
 * look identical from inside the app (an empty `pads`), and NONE OF THEM IS
 * FIXABLE IN THAT FILE. It was dev-only, behind `window.__AUTOMTG_RING`, which
 * is no use at all to somebody on a Deck in gaming mode with no devtools and no
 * keyboard.
 *
 * So this is that diagnosis, on screen, with the fix for each cause next to it.
 * It is deliberately blunt and deliberately specific: "No controller detected"
 * is a symptom, and a player who reads only a symptom concludes the game is
 * broken and stops.
 *
 * It polls rather than subscribing, because `getGamepads()` is a snapshot and
 * there is no connection event worth trusting -- `pad.ts`'s header point 4
 * records a whole session lost to believing otherwise. A second is far below
 * anybody's patience and costs one array read.
 */

import { useEffect, useState } from "react";
import { padDiagnostics } from "../../input/pad";
import { SchemePicker } from "./SchemePicker";

/** How often the panel re-reads the pad. See the header. */
const POLL_MS = 1000;

type Diagnostics = ReturnType<typeof padDiagnostics>;

/**
 * The three reasons `pads` is empty, in the order they are worth checking.
 *
 * SECURE CONTEXT IS FIRST AND THAT IS NOT ARBITRARY. The Gamepad API does not
 * exist at all over plain http to anything but localhost, so a Deck pointed at
 * `http://192.168.x.x:5173` -- which is exactly how somebody tests this on a
 * handheld -- has no `getGamepads` to fail, and every Steam-side fix below is
 * wasted effort until it is served over https. It is also the one nobody thinks
 * of, because the same URL works perfectly on the machine serving it.
 */
function causes(diag: Diagnostics): { when: boolean; title: string; body: string }[] {
  return [
    {
      when: !diag.secure || !diag.supported,
      title: "This page is not a secure context",
      body:
        "The Gamepad API only exists over https, or on localhost. Opening the game " +
        "by LAN address over plain http gives the browser no way to see a pad at all.",
    },
    {
      when: true,
      title: "Steam is sending a keyboard, not a gamepad",
      body:
        "Steam Input picks a keyboard-and-mouse template for browsers. In the game's " +
        "controller settings, change the layout template to Gamepad. Until you do, " +
        "Steam grabs the pad and the page never sees it.",
    },
    {
      when: true,
      title: "A Flatpak browser cannot reach the device",
      body:
        "If the browser was installed from Discover it is sandboxed away from the " +
        "hardware. In Desktop Mode run:  flatpak override --user " +
        "--filesystem=/run/udev:ro com.google.Chrome  then restart it.",
    },
    {
      when: !diag.focused,
      title: "The page is not focused",
      body: "No browser reports a pad to a background tab. Click the page and try again.",
    },
  ].filter((cause) => cause.when);
}

export function ControllerPanel() {
  const [diag, setDiag] = useState<Diagnostics>(() => padDiagnostics());

  useEffect(() => {
    const timer = setInterval(() => setDiag(padDiagnostics()), POLL_MS);
    return () => clearInterval(timer);
  }, []);

  const found = diag.pads.length > 0;

  return (
    <div className="ctrl" data-testid="controller-panel">
      <SchemePicker />

      <div className="ctrl__status" data-testid="controller-status">
        <h3 className="ctrl__h">Controller</h3>
        {found ? (
          <ul className="ctrl__pads">
            {diag.pads.map((pad) => (
              <li key={pad} className="ctrl__pad">
                {pad}
              </li>
            ))}
          </ul>
        ) : (
          <p className="ctrl__none">No controller detected.</p>
        )}
      </div>

      {/*
        Only when there is something to explain. A panel that lists three fixes
        under a pad that is working teaches the player to distrust it.
      */}
      {!found && (
        <ol className="ctrl__causes">
          {causes(diag).map((cause) => (
            <li key={cause.title} className="ctrl__cause">
              <b className="ctrl__causeh">{cause.title}</b>
              <span className="ctrl__causeb">{cause.body}</span>
            </li>
          ))}
        </ol>
      )}

      {/*
        The fallback, and it is a real one rather than a consolation: the whole
        board is reachable from the d-pad and two buttons, because the region
        trap gives way at its edge. Somebody who never gets the Gamepad API
        working can still finish a game.
      */}
      <p className="ctrl__foot">
        The d-pad, Enter and Esc alone can reach everything, so the game stays playable even
        when the pad is not detected.
      </p>
    </div>
  );
}
