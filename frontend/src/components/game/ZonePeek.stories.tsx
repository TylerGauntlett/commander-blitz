/**
 * Looking inside a zone.
 *
 * Driven entirely from `uiStore.peek`, so the stories set that rather than a
 * prop -- which also means they exercise the store reset the harness does
 * between stories, since a leaked `peek` would open the wrong modal.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent, within } from "storybook/test";
import { useUiStore } from "../../state/uiStore";
import { gameView, player } from "../../testing/fixtures";
import * as scenarios from "../../testing/scenarios";
import { ZonePeek } from "./ZonePeek";

const full = scenarios.fullZones().state;

const meta = {
  title: "Game/ZonePeek",
  component: ZonePeek,
} satisfies Meta<typeof ZonePeek>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Nothing peeked: the modal is not in the document at all. */
export const Closed: Story = {
  args: { state: full },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(canvas.queryByTestId("zone-peek")).toBeNull();
  },
};

export const Graveyard: Story = {
  args: { state: full },
  parameters: { automtg: { ui: { peek: { pid: 0, zone: "graveyard" } } } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Grizzly Bears");
    // Duplicates collapse here too -- two Forests are one slot carrying "x2",
    // not two cards. The viewer draws its own count rather than a `CardStack`.
    const counts = [...canvasElement.querySelectorAll(".peek__count")].map(
      (n) => n.textContent,
    );
    expect(counts, "the two Forests should have collapsed into one counted slot").toContain(
      "×2",
    );
  },
};

export const Exile: Story = {
  args: { state: full },
  parameters: { automtg: { ui: { peek: { pid: 0, zone: "exile" } } } },
};

export const CommandZone: Story = {
  args: { state: full },
  parameters: { automtg: { ui: { peek: { pid: 0, zone: "command" } } } },
};

export const Hand: Story = {
  args: { state: full },
  parameters: { automtg: { ui: { peek: { pid: 0, zone: "hand" } } } },
};

/**
 * Somebody else's hand.
 *
 * The server sends `hand: null` for every seat but the viewer, and the modal has
 * to say so rather than render an empty zone -- "they have no cards" and "you
 * may not see their cards" are different facts.
 */
export const HiddenHand: Story = {
  args: { state: full },
  parameters: { automtg: { ui: { peek: { pid: 1, zone: "hand" } } } },
};

/** An empty zone still opens, and says it is empty. */
export const EmptyZone: Story = {
  args: {
    state: gameView({ players: [player({ graveyard: [] }), player({ pid: 1, hand: null })] }),
  },
  parameters: { automtg: { ui: { peek: { pid: 0, zone: "graveyard" } } } },
};

/** Clicking the backdrop closes it, which is the only way out on a touch device. */
export const ClosingIt: Story = {
  args: { state: full },
  parameters: { automtg: { ui: { peek: { pid: 0, zone: "graveyard" } } } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Grizzly Bears");
    await userEvent.click(canvasElement.querySelector(".peek-backdrop") as HTMLElement);
    expect(useUiStore.getState().peek).toBeNull();
  },
};
