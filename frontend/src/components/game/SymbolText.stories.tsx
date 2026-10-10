/**
 * Rules text with its symbols drawn rather than spelled.
 *
 * The interesting cases are all about the *seam* between prose and pip: a cost
 * mid-sentence must sit on the baseline, and a paragraph with no symbols at all
 * must come out as ordinary text rather than a wrapper that changes its layout.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";
import { SymbolText } from "./SymbolText";

const meta = {
  title: "Game/SymbolText",
  component: SymbolText,
  parameters: { commanderblitz: { mount: "bare" } },
} satisfies Meta<typeof SymbolText>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Inline: Story = {
  args: { text: "{T}: Add {G}." },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByAltText("{T}");
    expect(canvasElement.querySelectorAll(".pip")).toHaveLength(2);
  },
};

export const MidSentence: Story = {
  args: {
    text: "Whenever an opponent casts a spell, you may draw a card unless that player pays {1}.",
  },
};

export const ActivatedAbility: Story = {
  args: { text: "{2}{U}{U}, {T}: Draw two cards, then discard a card." },
};

/** Hybrid and phyrexian became reachable through deck import: the oracle text
 *  of an imported card is displayed verbatim and is full of them. */
export const HybridCost: Story = {
  args: { text: "{W/U}{W/U}: Draw a card. {2/G}: Regenerate. {G/P}: Fight." },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByAltText("{G/P}");
    expect(canvasElement.querySelectorAll("img.pip")).toHaveLength(4);
  },
};

/** No symbols at all: the common case, and it must not be decorated. */
export const PlainProse: Story = {
  args: { text: "Trample. When this creature dies, you gain 5 life." },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Trample/);
    expect(canvasElement.querySelectorAll(".pip")).toHaveLength(0);
  },
};
