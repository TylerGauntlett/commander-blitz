/**
 * The card face, which is the design system's smallest complete statement.
 *
 * Everything here is a ratio of `--card-w`, so these stories are the first place
 * a broken cascade shows up: in jsdom the custom property never resolves and the
 * face falls back to a fixed 104px, which is why `tests/components.test.tsx` can
 * assert what the face *says* but nothing about how it sits.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { card } from "../../testing/fixtures";
import { CardFace } from "./CardFace";

const meta = {
  title: "Game/CardFace",
  component: CardFace,
  parameters: { automtg: { frame: "bare" } },
} satisfies Meta<typeof CardFace>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Board: Story = {
  args: { card: card({ name: "Grizzly Bears", mana_cost: "{1}{G}" }) },
};

export const Detail: Story = {
  args: {
    card: card({
      name: "Aesi, Tyrant of Gyre Strait",
      card_id: "aesi_tyrant_of_gyre_strait",
      type_line: "Legendary Creature — Serpent",
      mana_cost: "{4}{G}{U}",
      oracle_text:
        "Trample. Whenever you play a land, draw a card. You may play an additional land on each of your turns.",
      power: 5,
      toughness: 5,
      colors: ["G", "U"],
      keywords: ["trample"],
    }),
    variant: "detail",
  },
};

/** Loaded map, no printing: the hatched plate, drawn on purpose. */
export const NoArt: Story = {
  args: { card: card({ name: "Kraken Token", is_token: true }) },
  parameters: { automtg: { frame: "bare", art: "none" } },
};
