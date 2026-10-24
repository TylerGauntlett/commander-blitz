/**
 * Assertions worth making in more than one story.
 *
 * The action-id invariant is the one that earns this file. Every decision's
 * buttons must exist exactly once in the document, and the ways to break it are
 * all structural rather than local: an action promoted to the commit slab that
 * is not also removed from the list, a card's target variants rendered as one
 * row *and* as individual buttons, a modal that opens without the panel standing
 * down. Each of those is invisible in the component that caused it and obvious
 * in a count, so the count belongs somewhere every story can reach.
 */

import { expect } from "storybook/test";
import { MIN_CARD_W } from "../logic/cardSize";
import { type Floors, floorsFor } from "../logic/floors";

/** Every action id the surface put in the document, in document order. */
export function renderedActionIds(root: HTMLElement): string[] {
  return [...root.querySelectorAll("[data-action-id]")].map(
    (node) => node.getAttribute("data-action-id") ?? "",
  );
}

/**
 * No action is reachable twice.
 *
 * Not "the right actions are present" -- that is each story's own business --
 * but that whatever is present is present once.
 */
export function expectUniqueActionIds(root: HTMLElement): void {
  const ids = renderedActionIds(root);
  const seen = new Map<string, number>();
  for (const id of ids) seen.set(id, (seen.get(id) ?? 0) + 1);
  const duplicates = [...seen.entries()].filter(([, count]) => count > 1);
  expect(duplicates, "these action ids render more than once").toEqual([]);
}

/** Exactly this set of ids is reachable, order-insensitively. */
export function expectActionIds(root: HTMLElement, ids: string[]): void {
  expectUniqueActionIds(root);
  expect([...renderedActionIds(root)].sort()).toEqual([...ids].sort());
}

/**
 * A card is drawn above the solver's floor.
 *
 * `MIN_CARD_W` is not an arbitrary number: `cardSize.ts` sets it at the smallest
 * width `e2e/legibility.spec.ts` has actually demonstrated still reads. So a
 * card *at* the floor is the signature of the harness failing -- the cascade did
 * not reach the canvas, `useZoomFit` measured a table 0px tall, and everything
 * clamped. Shrinking towards the floor on a crowded board is the feature working;
 * sitting on it is the feature having nothing to measure.
 */
export function expectCardsSized(root: HTMLElement, selector = ".card"): void {
  const cards = [...root.querySelectorAll(selector)];
  expect(cards.length, `no cards matched ${selector}`).toBeGreaterThan(0);
  const width = cards[0].getBoundingClientRect().width;
  expect(
    width,
    "cards sit at the solver's floor, so the zoom measured nothing",
  ).toBeGreaterThan(MIN_CARD_W);
}

/** Nothing in `root` hangs outside `container`, on either axis. */
export function expectWithin(root: HTMLElement, container: HTMLElement, slack = 1): void {
  const bounds = container.getBoundingClientRect();
  for (const node of root.children) {
    const box = node.getBoundingClientRect();
    if (box.width === 0 && box.height === 0) continue;
    expect(box.left, "hangs off the left").toBeGreaterThanOrEqual(bounds.left - slack);
    expect(box.right, "hangs off the right").toBeLessThanOrEqual(bounds.right + slack);
  }
}

/**
 * Resolve a CSS length in the document the element lives in.
 *
 * A clamp of `vh` cannot be compared to a literal: a story runs in an iframe
 * whose height is not the window's, and `theme.css` has a media query keyed on
 * viewport height too. Writing the value onto a throwaway probe and reading it
 * back is the only way to get the number *this* document would have used.
 */
function resolveLength(el: HTMLElement, value: string): number {
  const probe = el.ownerDocument.createElement("div");
  probe.style.position = "absolute";
  probe.style.visibility = "hidden";
  probe.style.height = value;
  el.ownerDocument.body.appendChild(probe);
  const px = probe.getBoundingClientRect().height;
  probe.remove();
  return px;
}

/**
 * The component is the size its mount gives it in the app.
 *
 * Compared against `appGeometry.ts` -- the numbers `board.css` and `lobby.css`
 * state -- rather than against the mount that produced the box, because
 * comparing a thing to itself passes whatever it is. A failure means the story
 * lost its mount, or the app's layout moved and the stories now lie.
 */
export function expectMountedLike(
  el: HTMLElement,
  expected: { width?: number | string; height?: number | string; slack?: number },
): void {
  const slack = expected.slack ?? 1;
  const box = el.getBoundingClientRect();
  if (expected.width !== undefined) {
    const want =
      typeof expected.width === "number" ? expected.width : resolveLength(el, expected.width);
    expect(
      Math.abs(box.width - want),
      `width ${Math.round(box.width)}px, but the app gives this ${Math.round(want)}px`,
    ).toBeLessThanOrEqual(slack);
  }
  if (expected.height !== undefined) {
    const want =
      typeof expected.height === "number"
        ? expected.height
        : resolveLength(el, expected.height);
    expect(
      Math.abs(box.height - want),
      `height ${Math.round(box.height)}px, but the app gives this ${Math.round(want)}px`,
    ).toBeLessThanOrEqual(slack);
  }
}

/**
 * Wait until an element's transform stops changing.
 *
 * For the handful of stories that run with real motion, "has it started" and
 * "has it finished" are different questions and only the second is worth
 * asserting against. Waiting for a transform to merely *exist* returns on the
 * spring's first frame -- `matrix(1.0008, ...)` on its way to 1.02 -- so a story
 * measuring a hovered box measured it before the hover had happened, and passed
 * against the defect it was written for.
 */
export async function settled(el: HTMLElement, quietFrames = 3): Promise<void> {
  let last = "";
  let quiet = 0;
  for (let i = 0; i < 180 && quiet < quietFrames; i += 1) {
    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
    const now = getComputedStyle(el).transform;
    quiet = now === last ? quiet + 1 : 0;
    last = now;
  }
}

/* ==========================================================================
   The handheld floors, in CI
   ==========================================================================

   Type, target and card, per layout. `e2e/handheldAssert.ts` has
   asserted these against a real engine since Loop 3 -- but **Playwright is not
   in CI**, so until now nothing stopped a change landing that put a label back
   under the floor. `scripts/verify.py` does run the Storybook project, in a
   real Chromium with the real stylesheets, which is everything this walk needs.

   So this is not a second implementation of the gate; it is the same three
   numbers, asked of a component rather than of a game, on the one surface CI
   actually runs. The e2e gate keeps its wider job -- reachability, budgets,
   broken images, the ring -- which needs a live board to be worth asking.
   ========================================================================== */

/**
 * The floors for the layout the story is in: `logic/floors.ts` holds a row per
 * compact mode, and the viewport global stamps which one (ADR 0025).
 */
function floors(): Floors {
  return floorsFor(document.documentElement.getAttribute("data-layout"));
}

/**
 * Sub-pixel slack.
 *
 * A `clamp()` inside a `calc()` lands on fractions, and a box measured at
 * 43.98px is the same design as one measured at 44. Reporting it is how a gate
 * teaches people to ignore it.
 */
const SLACK = 0.5;

function describeEl(el: Element): string {
  const cls = (el.className || "").toString().trim().split(/\s+/).slice(0, 2).join(".");
  const id = el.getAttribute("data-testid") ?? el.getAttribute("data-stop");
  return `${el.tagName.toLowerCase()}${cls ? `.${cls}` : ""}${id ? `[${id}]` : ""}`;
}

/**
 * On screen, not merely laid out.
 *
 * The same walk `input/stops.ts` and `e2e/handheldAssert.ts` use, and for the
 * same reason: a clipped opponent's lane still reports its cards' full boxes,
 * so measuring without it reports failures at things nobody can see -- and the
 * "fix" would be to stop clipping the lanes, which would break the effects
 * anchoring instead.
 */
function onScreen(el: Element): boolean {
  const style = getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden") return false;
  if (Number.parseFloat(style.opacity) === 0) return false;
  const box = el.getBoundingClientRect();
  if (box.width <= 0 || box.height <= 0) return false;
  for (let a = el.parentElement; a; a = a.parentElement) {
    const s = getComputedStyle(a);
    if (s.overflow === "visible" && s.overflowX === "visible" && s.overflowY === "visible") {
      continue;
    }
    const clip = a.getBoundingClientRect();
    if (clip.width <= 0 || clip.height <= 0) return false;
    if (
      box.right <= clip.left ||
      box.left >= clip.right ||
      box.bottom <= clip.top ||
      box.top >= clip.bottom
    ) {
      return false;
    }
  }
  return true;
}

/**
 * Nothing carrying information is smaller than the floor.
 *
 * Only elements that OWN a text node are measured, and `aria-hidden` subtrees
 * are skipped. That is the honest line between a font-size floor and a
 * font-size ban: a wrapper inherits a size it never renders, and counting it
 * reports failures at elements with nothing in them.
 */
export function expectFontFloor(root: HTMLElement): void {
  const FLOORS = floors();
  const under: string[] = [];
  for (const el of root.querySelectorAll<HTMLElement>("*")) {
    if (el.closest("[aria-hidden='true']")) continue;
    const ownsText = [...el.childNodes].some(
      (n) => n.nodeType === 3 && (n.textContent ?? "").trim().length > 0,
    );
    if (!ownsText || !onScreen(el)) continue;
    const px = Number.parseFloat(getComputedStyle(el).fontSize);
    if (px + SLACK < FLOORS.font) {
      under.push(`${describeEl(el)} at ${Math.round(px * 100) / 100}px`);
    }
  }
  expect(under, `type under the ${FLOORS.font}px floor`).toEqual([]);
}

/**
 * Every control is big enough to hit with a thumb.
 *
 * Measured on the element's own border box. A control padded out by a
 * transparent parent -- the trick the zone chips use, a 21px chip inside a 44px
 * hit area -- passes because the *stop* is the outer box, which is the thing a
 * press actually lands on.
 */
export function expectHitFloor(root: HTMLElement): void {
  const FLOORS = floors();
  const small: string[] = [];
  const controls = root.querySelectorAll<HTMLElement>(
    "button, [role='button'], a[href], input, select, [data-stop]",
  );
  for (const el of controls) {
    if (el.hasAttribute("disabled") || !onScreen(el)) continue;
    const box = el.getBoundingClientRect();
    if (box.width + SLACK < FLOORS.hit || box.height + SLACK < FLOORS.hit) {
      small.push(`${describeEl(el)} at ${Math.round(box.width)}x${Math.round(box.height)}`);
    }
  }
  expect(small, `controls under the ${FLOORS.hit}px hit floor`).toEqual([]);
}

/**
 * Every card the ring can land on is big enough to read.
 *
 * Scoped to cards carrying a stop, because that is what "the ring can land on
 * it" means. A decorative thumbnail beside its own printed name -- the deck
 * catalogue's, the pod seat's -- is not a card you read, and is not a stop.
 */
export function expectCardFloor(root: HTMLElement): void {
  const FLOORS = floors();
  const small: string[] = [];
  for (const el of root.querySelectorAll<HTMLElement>(".card[data-stop], .face[data-stop]")) {
    if (!onScreen(el)) continue;
    const box = el.getBoundingClientRect();
    // A tapped card is rotated, so its border box measures as its own height.
    // `--card-w` is the number the design is stated in; read that instead.
    const declared = Number.parseFloat(getComputedStyle(el).getPropertyValue("--card-w"));
    const w = Number.isFinite(declared) && declared > 0 ? declared : box.width;
    if (w + SLACK < FLOORS.card) {
      small.push(`${describeEl(el)} at ${Math.round(w * 100) / 100}px`);
    }
  }
  expect(small, `cards under the ${FLOORS.card}px floor`).toEqual([]);
}

/** All three floors, which is how they are always wanted. */
export function expectHandheldFloors(root: HTMLElement): void {
  expectFontFloor(root);
  expectHitFloor(root);
  expectCardFloor(root);
}

/**
 * Nothing has been pushed off the bottom of anything.
 *
 * `scrollHeight > clientHeight` asks the question directly and does not care
 * what kind of element it is -- which matters, because the things that actually
 * went missing at 1200x800 during the playtest loops were band labels, the orb,
 * the pile counts and whole rows of the action list, none of which a
 * card-measuring check could see.
 *
 * Regions where scrolling IS the design are excluded by name, for the reason
 * `e2e/handheldAssert.ts` gives: a long action list and an opponent's clipped
 * lanes are meant to scroll, and a gate that forbade it would be demanding a
 * different feature.
 */
export function expectNothingOverflows(root: HTMLElement, allow: string[] = []): void {
  const over: string[] = [];
  for (const selector of [
    ".play__mine",
    ".play__mine .mat__side",
    ".play__opponents",
    ".table__foot",
    ".acts",
    ".track",
  ]) {
    // A story that POSES a scroll passes its own selector in. Named per story
    // rather than dropped from the list, so the exemption is visible at the
    // place that claims it rather than hidden in this file.
    if (allow.includes(selector)) continue;
    for (const el of root.querySelectorAll<HTMLElement>(selector)) {
      const by = el.scrollHeight - el.clientHeight;
      if (by > 2) over.push(`${selector} by ${by}px`);
    }
  }
  expect(over, "these regions hold more than they can show").toEqual([]);
}
