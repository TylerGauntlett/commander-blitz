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
import { expectHandheldFloors, settled } from "../../testing/asserts";
import { gameView, player } from "../../testing/fixtures";
import * as scenarios from "../../testing/scenarios";
import { ZonePeek } from "./ZonePeek";

const full = scenarios.fullZones().state;

const meta = {
  title: "Game/ZonePeek",
  component: ZonePeek,
  parameters: { commanderblitz: { mount: "screen" } },
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
  parameters: { commanderblitz: { ui: { peek: { pid: 0, zone: "graveyard" } } } },
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
  parameters: { commanderblitz: { ui: { peek: { pid: 0, zone: "exile" } } } },
};

export const CommandZone: Story = {
  args: { state: full },
  parameters: { commanderblitz: { ui: { peek: { pid: 0, zone: "command" } } } },
};

export const Hand: Story = {
  args: { state: full },
  parameters: { commanderblitz: { ui: { peek: { pid: 0, zone: "hand" } } } },
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
  parameters: { commanderblitz: { ui: { peek: { pid: 1, zone: "hand" } } } },
};

/** An empty zone still opens, and says it is empty. */
export const EmptyZone: Story = {
  args: {
    state: gameView({ players: [player({ graveyard: [] }), player({ pid: 1, hand: null })] }),
  },
  parameters: { commanderblitz: { ui: { peek: { pid: 0, zone: "graveyard" } } } },
};

/**
 * How each card got here.
 *
 * The durable half of the exit animation. The ghost answers "why did that die"
 * for about a second; this is where a player who was not watching closely comes
 * to find out afterwards which of their creatures was exiled, and with what.
 *
 * Note the two Forests: they collapse into one counted slot, and the note
 * describes the copy actually on top rather than claiming to speak for both.
 */
export const WithRemovalNotes: Story = {
  args: {
    state: full,
    reasons: new Map([
      [870, "Destroyed by Swords to Plowshares"],
      [871, "Sacrificed to Zuran Orb"],
      [873, "Lethal damage"],
    ]),
  },
  parameters: { commanderblitz: { ui: { peek: { pid: 0, zone: "graveyard" } } } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Destroyed by Swords to Plowshares");
    // Cultivate is in the pile with a note; the second Forest is folded away.
    expect(canvas.getAllByTestId("peek-note").length).toBeGreaterThanOrEqual(2);
  },
};

/** The same in exile, where the question is usually more urgent. */
export const ExileWithNotes: Story = {
  args: { state: full, reasons: new Map([[880, "Exiled by Leyline of the Void"]]) },
  parameters: { commanderblitz: { ui: { peek: { pid: 0, zone: "exile" } } } },
  play: async ({ canvasElement }) => {
    await within(canvasElement).findByText("Exiled by Leyline of the Void");
  },
};

/** Clicking the backdrop closes it, which is the only way out on a touch device. */
export const ClosingIt: Story = {
  args: { state: full },
  parameters: { commanderblitz: { ui: { peek: { pid: 0, zone: "graveyard" } } } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Grizzly Bears");
    await userEvent.click(canvasElement.querySelector(".peek-backdrop") as HTMLElement);
    expect(useUiStore.getState().peek).toBeNull();
  },
};

/** The graveyard modal on a Deck: the pile's cards are readable. */
export const GraveyardHandheld: Story = {
  args: Graveyard.args,
  globals: { viewport: { value: "deck" } },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    await settled(canvasElement);
    expectHandheldFloors(canvasElement);
  },
};
