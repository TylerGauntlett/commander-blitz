/**
 * The right rail's large card.
 *
 * The panel is a *fixed* height whether it holds a card or not. It used to size
 * to its content, which meant the whole action panel below it jumped every time
 * the pointer crossed a card -- and jumped again between a creature and a land,
 * because a land has no P/T row and shorter rules. That is a measurement, so it
 * is checked here and nowhere else.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";
import { useUiStore } from "../../state/uiStore";
import * as scenarios from "../../testing/scenarios";
import { CardPreview } from "./CardPreview";

const board = scenarios.earlyBoard().state;
const combat = scenarios.combatDeclareAttackers().state;

const meta = {
  title: "Game/CardPreview",
  component: CardPreview,
  parameters: { automtg: { mount: "railRight" } },
} satisfies Meta<typeof CardPreview>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Nothing hovered: the prompt, at the same height as a card. */
export const Nothing: Story = {
  args: { state: board },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Hover a card/i);
  },
};

export const HoveredCreature: Story = {
  args: { state: board },
  parameters: { automtg: { mount: "railRight", ui: { hoveredOid: 205 } } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Llanowar Elves");
    // A creature's status line says where it is and what it is doing.
    await canvas.findByText(/battlefield/i);
  },
};

export const HoveredLand: Story = {
  args: { state: board },
  parameters: { automtg: { mount: "railRight", ui: { hoveredOid: 204 } } },
};

export const HoveredCommander: Story = {
  args: { state: board },
  parameters: { automtg: { mount: "railRight", ui: { hoveredOid: 900 } } },
};

/** An attacker: the status line leads with what it is doing, not where it is. */
export const HoveredAttacker: Story = {
  args: { state: combat },
  parameters: { automtg: { mount: "railRight", ui: { hoveredOid: 302 } } },
};

/**
 * The panel is the same height whatever it is holding.
 *
 * This is the actual property, and it is a *comparison* rather than a number:
 * the panel used to size to its content, so the whole action panel below it
 * jumped every time the pointer crossed a card -- and jumped again between a
 * creature and a land, because a land has no P/T row and shorter rules. Those
 * three are rendered side by side and their heights simply have to match.
 *
 * Deliberately not asserted as "taller than N": the absolute height comes from
 * the rail's grid track, which a bare story does not have. What must hold
 * everywhere is that the three agree.
 */
export const HeightDoesNotChange: Story = {
  args: { state: board },
  parameters: { automtg: { mount: "railRight" } },
  /*
   * Rendered inside the right rail on purpose. The fixed height is
   * `.rail--right .preview { height: clamp(240px, 34vh, 420px) }` -- it is a
   * property of the panel *in its rail*, not of the component, and outside one
   * sizing to content is the correct behaviour. A story that dropped the
   * wrapper would be asserting against a layout the app never renders.
   */
  render: (args) => (
    <aside className="rail rail--right" style={{ height: "100vh", width: 320 }}>
      <CardPreview {...args} />
    </aside>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const pane = await canvas.findByTestId("card-preview");
    const heightNow = () => Math.round(pane.getBoundingClientRect().height);

    // One panel, measured as the hover moves -- which is what the player does,
    // and the only way to pose it: `hoveredOid` is global, so two instances
    // side by side would always be showing the same card.
    const empty = heightNow();

    useUiStore.setState({ hoveredOid: 205 });
    await canvas.findByText("Llanowar Elves");
    const creature = heightNow();

    useUiStore.setState({ hoveredOid: 204 });
    await canvas.findByText("Breeding Pool");
    const land = heightNow();

    expect(
      new Set([empty, creature, land]).size,
      `the rail jumps: empty ${empty}, creature ${creature}, land ${land}`,
    ).toBe(1);
  },
};
