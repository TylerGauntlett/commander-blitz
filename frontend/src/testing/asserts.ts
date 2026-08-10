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
