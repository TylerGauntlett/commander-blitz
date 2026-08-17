/**
 * Whether to move things, asked once and answerable by a test.
 *
 * The board is gaining effects that are *only* motion -- particles, lunges,
 * screen shake -- and a player who has asked their system for reduced motion
 * should not get any of them. What they must still get is everything that
 * carries meaning: damage numerals, exit captions, flashes, the log. The split
 * is "how it felt" versus "what happened", and only the first is dropped.
 *
 * ## Why this is not just a media query
 *
 * Headless Chromium reports `prefers-reduced-motion: reduce`. Storybook already
 * works around that for Framer by passing `reducedMotion="never"` to
 * `MotionConfig` in its opt-in stories, but `MotionConfig` is React context and
 * cannot be read from a canvas draw loop or a module-level `burst()` call. So
 * the override is explicit and global, and `preview.tsx` sets it alongside the
 * `MotionConfig` it already sets. Without it, every particle story would render
 * an empty canvas in the one environment built to look at them.
 */

/** `null` defers to the system; a boolean overrides it. */
let override: boolean | null = null;

let query: MediaQueryList | null = null;
let queried = false;

function media(): MediaQueryList | null {
  if (queried) return query;
  queried = true;
  try {
    query = window.matchMedia("(prefers-reduced-motion: reduce)");
  } catch {
    // No `matchMedia` at all: jsdom without the shim, or a very old browser.
    query = null;
  }
  return query;
}

export function prefersReducedMotion(): boolean {
  if (override !== null) return override;
  return media()?.matches === true;
}

/**
 * Force the answer, or pass `null` to defer to the system again.
 *
 * Storybook's `preview.tsx` and the e2e helpers are the callers. Application
 * code must not use this -- it is a test seam, not a setting.
 */
export function setReducedMotionOverride(value: boolean | null): void {
  override = value;
}
