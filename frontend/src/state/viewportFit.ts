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

/** What the screen reports, for a bug report from a device with no devtools. */
export interface ScreenFacts {
  /** `standalone` for an installed web app, `browser` for a tab. */
  mode: string;
  viewport: string;
  screen: string;
  scale: string;
  /** `env(safe-area-inset-*)` as the page resolves it, e.g. `t0 r90 b0 l0`. */
  insets: string;
  tag: string;
  statusBar: string;
}

/**
 * The facts `viewportFit` decides from and the ones iOS decides for it.
 *
 * Read off the live document, so a screenshot of Settings answers whether an
 * installed app is drawn under the status bar: an inset of 0 on the side the
 * bar is on means iOS kept that strip for itself, whatever the page asked for.
 */
export function screenFacts(): ScreenFacts {
  const probe = document.createElement("div");
  probe.style.cssText =
    "position:fixed;visibility:hidden;pointer-events:none;" +
    "padding:env(safe-area-inset-top,0px) env(safe-area-inset-right,0px) " +
    "env(safe-area-inset-bottom,0px) env(safe-area-inset-left,0px)";
  document.body.appendChild(probe);
  const style = getComputedStyle(probe);
  const sides: [string, string][] = [
    ["t", style.paddingTop],
    ["r", style.paddingRight],
    ["b", style.paddingBottom],
    ["l", style.paddingLeft],
  ];
  const insets = sides
    .map(([side, value]) => `${side}${Math.round(Number.parseFloat(value) || 0)}`)
    .join(" ");
  probe.remove();
  const standalone =
    window.matchMedia?.("(display-mode: standalone)").matches ||
    (navigator as { standalone?: boolean }).standalone === true;
  return {
    mode: standalone ? "standalone" : "browser",
    viewport: `${window.innerWidth} x ${window.innerHeight}`,
    screen: `${window.screen.width} x ${window.screen.height}`,
    scale: (window.visualViewport?.scale ?? 1).toFixed(3),
    insets,
    tag: tag()?.getAttribute("content") ?? "none",
    statusBar:
      document
        .querySelector<HTMLMetaElement>('meta[name="apple-mobile-web-app-status-bar-style"]')
        ?.getAttribute("content") ?? "none",
  };
}
