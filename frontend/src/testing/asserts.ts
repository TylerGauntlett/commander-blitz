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
