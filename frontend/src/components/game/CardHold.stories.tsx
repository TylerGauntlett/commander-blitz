/**
 * The full-screen read, held on `Y`.
 *
 * A picture and its text, over the whole board, with nothing in it to press.
 * What a story can check that jsdom cannot is the size: the whole point of the
 * hold is that the card is bigger than the rail's reader, and on a Deck the
 * card floor is the least it may be.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { expectHandheldFloors } from "../../testing/asserts";
import * as pool from "../../testing/cards";
import { CardHold } from "./CardHold";

const meta = {
  title: "Game/CardHold",
  component: CardHold,
  parameters: { commanderblitz: { mount: "tableOverlay" } },
} satisfies Meta<typeof CardHold>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Six lines of rules, which is the card the hold exists for. */
export const HeldOpen: Story = {
  args: { card: pool.aesi({ oid: 900 }) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Aesi/);
    const hold = canvasElement.querySelector<HTMLElement>("[data-testid='card-hold']");
    expect(hold?.hasAttribute("data-modal-root")).toBe(true);
    // Bigger than the rail's reader: the big variant is 330px wide by design.
    const card = hold?.querySelector<HTMLElement>(".hold__card .card");
    expect(card?.getBoundingClientRect().width).toBeGreaterThanOrEqual(300);
    // Nothing to press, so nothing for the ring to land on.
    expect(hold?.querySelectorAll("[data-stop], [data-action-id]").length).toBe(0);
  },
};

/** A card's proportions, whatever the text: the frame is 5:7 of its width. */
const expectCardShaped = (canvasElement: HTMLElement) => {
  const frame = canvasElement.querySelector<HTMLElement>(".hold__card");
  const box = frame?.getBoundingClientRect();
  expect(box).toBeTruthy();
  if (!box) return;
  expect(box.width).toBeGreaterThanOrEqual(300);
  expect(Math.abs(box.height - box.width * 1.4), "the hold is card-shaped").toBeLessThan(2);
};

/**
 * The same, on a Deck: the card is still at least the floor, the text is
 * legible, and THE FRAME IS A CARD'S SHAPE. On a desktop the hold is as tall
 * as its text; here it is the only thing on the screen and every card is the
 * same size, with the rules scrolling inside it.
 */
export const HeldOpenHandheld: Story = {
  args: { card: pool.aesi({ oid: 900 }) },
  globals: { handheld: "on" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Aesi/);
    expectHandheldFloors(canvasElement);
    expectCardShaped(canvasElement);
    // Six lines of rules at the 16px floor do not fit a 5:7 frame; they scroll.
    const rules = canvasElement.querySelector<HTMLElement>(".hold__card .face__rules");
    expect(rules && getComputedStyle(rules).overflowY).toBe("auto");
  },
};

/** ...and a card with one line of text is exactly the same size. */
export const HeldOpenHandheldShortText: Story = {
  args: { card: pool.grizzlyBears({ oid: 901 }) },
  globals: { handheld: "on" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Grizzly Bears/);
    expectCardShaped(canvasElement);
  },
};

/** Nothing held: nothing drawn. */
export const Closed: Story = {
  args: { card: null },
  play: async ({ canvasElement }) => {
    expect(canvasElement.querySelector("[data-testid='card-hold']")).toBeNull();
  },
};

/**
 * Opened from a mouse: right-click a card, or `i` over it.
 *
 * What only a browser can say: the whole card is drawn -- not clipped to the
 * rail's fixed frame, which is why the desktop wanted this at all -- and the
 * backdrop takes the click that puts it away, rather than letting it through
 * to the board card underneath. The Close button is a 44px target and still
 * not a stop.
 */
export const OpenedFromAMouse: Story = {
  args: { card: pool.aesi({ oid: 900 }), onClose: fn() },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Aesi/);
    const hold = canvasElement.querySelector<HTMLElement>("[data-testid='card-hold']");
    expect(hold?.getAttribute("role")).toBe("dialog");
    expect(hold && getComputedStyle(hold).pointerEvents).toBe("auto");

    // Unclipped: the card's own content fits inside it with nothing hidden.
    const face = hold?.querySelector<HTMLElement>(".hold__card .card");
    const frame = hold?.querySelector<HTMLElement>(".hold__card");
    expect(frame && frame.scrollHeight - frame.clientHeight).toBeLessThanOrEqual(1);
    expect(face?.getBoundingClientRect().width).toBeGreaterThanOrEqual(300);

    const close = canvas.getByTestId("card-hold-close");
    expect(close.hasAttribute("data-stop")).toBe(false);
    const box = close.getBoundingClientRect();
    expect(Math.min(box.width, box.height)).toBeGreaterThanOrEqual(44);

    // A click on the card is reading it, not leaving it.
    await userEvent.click(face as HTMLElement);
    expect(args.onClose).not.toHaveBeenCalled();
    await userEvent.click(close);
    expect(args.onClose).toHaveBeenCalledTimes(1);
  },
};
