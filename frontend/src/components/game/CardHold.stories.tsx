/**
 * The full-screen read, held on `Y`.
 *
 * A picture and its text, over the whole board, with nothing in it to press.
 * What a story can check that jsdom cannot is the size: the whole point of the
 * hold is that the card is bigger than the rail's reader, and on a Deck the
 * card floor is the least it may be.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";
import { expectHandheldFloors } from "../../testing/asserts";
import * as pool from "../../testing/cards";
import { CardHold } from "./CardHold";

const meta = {
  title: "Game/CardHold",
  component: CardHold,
  parameters: { automtg: { mount: "tableOverlay" } },
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

/** The same, on a Deck: the card is still at least the floor, and the text is legible. */
export const HeldOpenHandheld: Story = {
  args: { card: pool.aesi({ oid: 900 }) },
  globals: { handheld: "on" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Aesi/);
    expectHandheldFloors(canvasElement);
  },
};

/** Nothing held: nothing drawn. */
export const Closed: Story = {
  args: { card: null },
  play: async ({ canvasElement }) => {
    expect(canvasElement.querySelector("[data-testid='card-hold']")).toBeNull();
  },
};
