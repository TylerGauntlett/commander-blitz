/**
 * Identical permanents, collapsed into one pile.
 *
 * Nine Forests as nine cards is nine times the board for one fact. The pile
 * carries a count and fans on hover -- and every member stays mounted the whole
 * time, so a `layoutId` animation out of the pile has something to animate from.
 *
 * All of that is geometry: the fan is an offset per member, and "still mounted"
 * is a claim about the DOM under a hover.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, waitFor, within } from "storybook/test";
import { cardWidthPx } from "../../logic/cardSize";
import { stackCards } from "../../logic/stacking";
import * as pool from "../../testing/cards";
import { CardStack } from "./CardStack";

/** `count` copies of one card, grouped exactly as the board would group them. */
function pile(count: number) {
  const cards = Array.from({ length: count }, (_, i) => pool.forest({ oid: 100 + i }));
  return stackCards(cards)[0];
}

const meta = {
  title: "Game/CardStack",
  component: CardStack,
  parameters: { automtg: { frame: "bare" } },
  args: { cardWidth: cardWidthPx(96, 1), onActivate: fn(), onDropOn: fn() },
} satisfies Meta<typeof CardStack>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * One card is not a pile, and must not grow a count badge.
 *
 * `data-stack-count` is always on the container -- it is the group's size, and
 * e2e reads it either way. The *badge* is what must not appear, because "x1" is
 * a label that tells the player nothing they cannot already see.
 */
export const Single: Story = {
  args: { group: pile(1) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Forest");
    const stack = canvasElement.querySelector("[data-stack-count]");
    expect(stack?.getAttribute("data-stack-count")).toBe("1");
    expect(canvasElement.querySelector(".cardstack__count")).toBeNull();
  },
};

export const Two: Story = { args: { group: pile(2) } };

export const Nine: Story = {
  args: { group: pile(9) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findAllByText("Forest");
    const badge = canvasElement.querySelector("[data-stack-count]");
    expect(badge?.getAttribute("data-stack-count")).toBe("9");

    // Every member stays mounted, closed or not -- that is what lets a card
    // animate *out* of the pile rather than appearing beside it.
    expect(canvasElement.querySelectorAll(".card")).toHaveLength(9);
  },
};

/**
 * Fanned open.
 *
 * The members really do separate: closed, they sit on each other; open, each is
 * offset from the last. Comparing the two is the only way to state it.
 */
export const FansOnHover: Story = {
  args: { group: pile(5) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const cards = await canvas.findAllByText("Forest");
    const lefts = () =>
      [...canvasElement.querySelectorAll(".card")].map((c) =>
        Math.round(c.getBoundingClientRect().left),
      );

    const closed = new Set(lefts()).size;
    await userEvent.hover(cards[0]);

    // Waited for, because the fan is animated and the positions arrive a frame
    // after the hover. Read synchronously this passed on a quiet machine and
    // failed under load, which is the worst kind of green.
    await waitFor(() =>
      expect(
        new Set(lefts()).size,
        "the pile did not fan: every card is still at the same x",
      ).toBeGreaterThan(closed),
    );
  },
};

/** A pile of tapped lands, which is what a spent turn looks like. */
export const AllTapped: Story = {
  args: {
    group: (() => {
      const cards = Array.from({ length: 6 }, (_, i) =>
        pool.forest({ oid: 200 + i, tapped: true }),
      );
      return stackCards(cards)[0];
    })(),
  },
};

/** Tokens stack too, by name and printed characteristics. */
export const Tokens: Story = {
  args: {
    group: (() => {
      const cards = Array.from({ length: 4 }, (_, i) => pool.krakenToken({ oid: 300 + i }));
      return stackCards(cards)[0];
    })(),
  },
};
