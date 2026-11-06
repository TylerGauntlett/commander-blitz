/**
 * Writes the viewport tag `logic/viewportScale.ts` decides on, and keeps it right.
 *
 * Imported for its side effect by `main.tsx`, before the first render, so the
 * table never lays out once at the short height and then again at the design
 * height. Three things make this more than one `setAttribute`:
 *
 * - **The decision needs the natural size, and a scaled page cannot see it.**
 *   Once the tag is written, `innerWidth`/`innerHeight` are the scaled layout's.
 *   So the size the tag was solved from is remembered with what it should
 *   produce, and a viewport that stops matching that (a rotation, a browser bar
 *   arriving) puts the natural tag back, lets the browser report its real size,
 *   and solves again. A resize this module caused matches, and is not a change.
 * - **A desktop browser ignores the tag.** The write is checked once it has had
 *   time to land; if the height did not move, the tag is put back and nothing
 *   here runs again for the life of the page. A desktop window the size of a
 *   tablet is the player's to zoom.
 * - **The Deck never gets here.** It is 1280x800, the design size, so its tag
 *   is the natural one and this module writes nothing.
 */

import {
  HANDHELD_DESIGN_H,
  layoutWidth,
  NATURAL_VIEWPORT,
  viewportContent,
} from "../logic/viewportScale";

/** How long a browser gets to apply a new tag before it is judged to ignore it. */
const SETTLE_MS = 400;

/** CSS pixels of disagreement that are rounding, not a different screen. */
const SLACK = 3;

interface Applied {
  width: number;
  height: number;
}

let applied: Applied | null = null;
let settling = false;
let ignored = false;

function tag(): HTMLMetaElement | null {
  return document.querySelector<HTMLMetaElement>('meta[name="viewport"]');
}

function near(a: number, b: number): boolean {
  return Math.abs(a - b) <= SLACK;
}

export function fitViewport(): void {
  if (ignored || settling) return;
  const meta = tag();
  if (!meta) return;

  if (applied) {
    if (near(window.innerWidth, applied.width) && near(window.innerHeight, applied.height))
      return;
    // The screen changed under the scale. Measure it unscaled, then solve again:
    // the browser's own resize brings us back here, and the timer covers one
    // that does not fire.
    applied = null;
    meta.setAttribute("content", NATURAL_VIEWPORT);
    window.setTimeout(fitViewport, SETTLE_MS);
    return;
  }

  const width = window.innerWidth;
  const height = window.innerHeight;
  const content = viewportContent(width, height);
  if (content === NATURAL_VIEWPORT) {
    if (meta.getAttribute("content") !== NATURAL_VIEWPORT)
      meta.setAttribute("content", content);
    return;
  }

  const expected: Applied = {
    width: layoutWidth(width, height),
    height: HANDHELD_DESIGN_H,
  };
  meta.setAttribute("content", content);
  settling = true;
  window.setTimeout(() => {
    settling = false;
    if (near(window.innerHeight, height) && !near(height, expected.height)) {
      // Nothing moved: this browser does not read the tag.
      ignored = true;
      meta.setAttribute("content", NATURAL_VIEWPORT);
      return;
    }
    applied = expected;
    // A rotation inside the settle window would otherwise go unanswered.
    fitViewport();
  }, SETTLE_MS);
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  fitViewport();
  window.addEventListener("resize", fitViewport);
}
