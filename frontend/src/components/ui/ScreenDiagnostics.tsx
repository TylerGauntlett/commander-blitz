/**
 * What the screen reports, in Settings, beside the controller's diagnostics.
 *
 * An installed web app on a phone has no devtools, and whether iOS lets the page
 * draw under its status bar is decided on the device, out of the page's reach:
 * the safe-area insets and the viewport are the evidence. A screenshot of this
 * panel is the whole bug report. Re-read on resize, so turning the device
 * updates it.
 */

import { useEffect, useState } from "react";
import { type ScreenFacts, screenFacts } from "../../state/viewportFit";

const ROWS: [keyof ScreenFacts, string][] = [
  ["mode", "Display"],
  ["viewport", "Viewport"],
  ["screen", "Screen"],
  ["scale", "Scale"],
  ["insets", "Safe area"],
  ["tag", "Viewport tag"],
  ["statusBar", "Status bar"],
];

export function ScreenDiagnostics() {
  const [facts, setFacts] = useState<ScreenFacts>(() => screenFacts());

  useEffect(() => {
    const read = () => setFacts(screenFacts());
    window.addEventListener("resize", read);
    return () => window.removeEventListener("resize", read);
  }, []);

  return (
    <div className="ctrl__status" data-testid="screen-diagnostics">
      <h3 className="ctrl__h">Screen</h3>
      <dl className="ctrl__diag">
        {ROWS.map(([key, label]) => (
          <div key={key} className="ctrl__diagrow">
            <dt>{label}</dt>
            <dd data-testid={`screen-${key}`}>{facts[key]}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
