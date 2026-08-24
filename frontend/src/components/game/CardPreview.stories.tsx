/**
 * The right rail's large card, and the reader it becomes at 1280x800.
 *
 * The panel is a *fixed* height whether it holds a card or not. It used to size
 * to its content, which meant the whole action panel below it jumped every time
 * the pointer crossed a card -- and jumped again between a creature and a land,
 * because a land has no P/T row and shorter rules. That is a measurement, so it
 * is checked here and nowhere else.
 *
 * The compressed stories at the bottom are the same component with the Layout
 * toolbar on. What they are worth looking at for is that a 243px rail cannot
 * hold a card FRAME -- one would be 116px across, smaller than the board card
 * it is meant to be helping you read -- so the picture becomes a landscape
 * window onto the same `art_crop` and the height that buys goes to the rules.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, waitFor, within } from "storybook/test";
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

/* --------------------------------------------------------------- compressed */

/** A creature: the P/T is stamped on the picture, not on the type line. */
export const ReaderCreature: Story = {
  args: { state: board },
  globals: { handheld: "on" },
  tags: ["handheld"],
  parameters: { automtg: { mount: "railRight", ui: { hoveredOid: 205 } } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Llanowar Elves");
    /*
     * The first draft put "Creature — Elf Druid · 1/1" on one 227px line. It
     * ellipsised, and the half it dropped was the number -- so the P/T moved on
     * to the art window, where a card keeps it.
     */
    expect(canvasElement.querySelector(".reader__pt")?.textContent).toBe("1/1");
    expect(canvasElement.querySelector(".reader__tl")?.textContent).toContain("Creature");
    // The desktop fact list is not carried: keywords are in the rules, status
    // is the tap state, the controller is whose mat it is on.
    expect(canvasElement.querySelector(".preview__facts")).toBeNull();
  },
};

/** A land: no P/T, and the rules box is most of the panel. */
export const ReaderLand: Story = {
  args: { state: board },
  globals: { handheld: "on" },
  tags: ["handheld"],
  parameters: { automtg: { mount: "railRight", ui: { hoveredOid: 204 } } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("card-preview");
    expect(canvasElement.querySelector(".reader__pt")).toBeNull();
  },
};

/**
 * The panel holds its height whatever the card is.
 *
 * This is the whole reason it is fixed: content-sized it is 179px on "Trample."
 * and 260 on three clauses, so the action list below would grow and shrink and
 * every row would slide under the cursor mid-decision.
 */
export const ReaderHoldsItsHeight: Story = {
  args: { state: board },
  globals: { handheld: "on" },
  tags: ["handheld"],
  parameters: { automtg: { mount: "railRight", ui: { hoveredOid: 205 } } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const panel = await canvas.findByTestId("card-preview");
    const withCard = panel.getBoundingClientRect().height;

    useUiStore.getState().hover(null);
    await waitFor(() => {
      expect(canvasElement.querySelector(".reader__body")).toBeNull();
    });

    expect(panel.getBoundingClientRect().height).toBeCloseTo(withCard, 0);
  },
};

/**
 * Nothing pointed at, in the compact rail.
 *
 * The idle line is worded for the input that is actually driving: a controller
 * player does not hover anything.
 */
export const ReaderIdle: Story = {
  args: { state: board },
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Point at a card/i);
  },
};

/**
 * A card in hand you cannot cast -- and the reader does NOT say why.
 *
 * It used to. "Needs {4}{G}{G}{G} -- you have {G}" is two lines at the 16px
 * floor and it was `flex: none`, so the height came out of the rules box, which
 * is the half of this panel a player opened it for: Elder Deep-Fiend was cut
 * 75px into its own paragraph. The sentence is a fact about the hand rather
 * than about the card, and `HandFan` draws it there as `.hand__hint` -- no
 * longer suppressed on a handheld. This story is the one that would notice it
 * coming back.
 */
export const ReaderUnplayable: Story = {
  args: { state: scenarios.openingHand().state },
  globals: { handheld: "on" },
  tags: ["handheld"],
  parameters: {
    automtg: {
      mount: "railRight",
      ui: { hoveredOid: scenarios.openingHand().state.players[0].hand?.[0]?.oid ?? null },
    },
  },
};
