/**
 * The stack, top first, floating over the board.
 *
 * Drawn as real card faces at an offset rather than a list of names, so the pile
 * is the one place the client has to compute a container height in pixels: the
 * items are absolutely positioned, so nothing can size to them.
 *
 * It used to be the top panel of a left rail. That rail is retired -- a 232px
 * column stood open all game for a thing that is empty for most of a turn and
 * urgent the moment it is not -- so it is a grid item sharing `.play`'s second
 * cell with the viewer's own mat, and grows down over their panel.
 *
 * Mounted at `play` for that reason, and the mount is load-bearing rather than
 * decorative: the pile is placed by `grid-row: 2`, so in any other grid it
 * lands in whatever that grid's second row happens to be. Mounted one level up
 * at `tableBody` it drew itself in the FOOT, which `npm run audit:stories`
 * caught as four stories bleeding 130px below the fold.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";
import { expectHandheldFloors } from "../../testing/asserts";
import * as pool from "../../testing/cards";
import { gameView, stackItem } from "../../testing/fixtures";
import * as scenarios from "../../testing/scenarios";
import { StackPanel } from "./StackPanel";

const meta = {
  title: "Game/StackPanel",
  component: StackPanel,
  parameters: { automtg: { mount: "play" } },
} satisfies Meta<typeof StackPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = {
  args: { state: gameView() },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("empty");
  },
};

export const OneSpell: Story = {
  args: {
    state: gameView({
      stack: [stackItem({ sid: 1, card: pool.thragtusk({ oid: 20, zone: "stack" }) })],
    }),
  },
};

/**
 * Three deep, and the order is the whole point.
 *
 * The stack resolves last-in first-out, so the panel draws it top first --
 * the trigger above the counter above the creature spell it answers.
 */
export const ThreeDeepWithCounterspell: Story = {
  args: { state: scenarios.stackThreeDeep().state },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const panel = await canvas.findByTestId("stack-panel");
    expect(panel.textContent).toContain("3");

    // Top first: whatever resolves next is drawn nearest the reader.
    const names = [...panel.querySelectorAll(".face__name")].map((n) => n.textContent);
    expect(names[0]).toContain("Rhystic Study");
    expect(names[names.length - 1]).toContain("Thragtusk");

    // The pile is absolutely positioned, so its height is computed rather than
    // declared. Zero here means the items are stacked on top of each other.
    const pile = panel.querySelector(".stackpile") as HTMLElement;
    expect(pile.getBoundingClientRect().height).toBeGreaterThan(0);
  },
};

export const TriggeredAbility: Story = {
  args: {
    state: gameView({
      stack: [
        stackItem({
          sid: 1,
          kind: "trigger",
          card: pool.rhysticStudy({ oid: 30 }),
          source_oid: 30,
          name: "Rhystic Study",
          description: "Rhystic Study: draw unless that player pays {1}",
        }),
      ],
    }),
  },
};

/** A deep stack: five items, to check the pile keeps growing its container. */
export const FiveDeep: Story = {
  args: {
    state: gameView({
      stack: [
        stackItem({ sid: 1, card: pool.thragtusk({ oid: 20, zone: "stack" }) }),
        stackItem({ sid: 2, card: pool.counterspell({ oid: 21, zone: "stack" }) }),
        stackItem({ sid: 3, card: pool.cultivate({ oid: 22, zone: "stack" }) }),
        stackItem({ sid: 4, card: pool.simicCharm({ oid: 23, zone: "stack" }) }),
        stackItem({ sid: 5, card: pool.serraAngel({ oid: 24, zone: "stack" }) }),
      ],
    }),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const panel = await canvas.findByTestId("stack-panel");
    const items = panel.querySelectorAll("[data-stack-sid]");
    expect(items).toHaveLength(5);
    // Each ply sits below the one above it, or the pile is a single card.
    const tops = [...items].map((i) => i.getBoundingClientRect().top);
    expect(new Set(tops).size, "the stack items are superimposed").toBe(5);
  },
};

/** Three deep on a Deck: the pile's faces stay readable. */
export const ThreeDeepHandheld: Story = {
  args: { state: scenarios.stackThreeDeep().state },
  globals: { handheld: "on" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("next");
    expectHandheldFloors(canvasElement);
  },
};
