/**
 * The deck browser, where the card *is* the control.
 *
 * There is no list with a button beside it: you pick a deck by clicking its
 * commander. That makes the catalogue a grid of real faces, which is why it
 * needs its card queries seeded to render on first paint.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { cardResponse } from "../../testing/fixtures";
import * as pods from "../../testing/pods";
import { DeckCatalog } from "./DeckCatalog";

/** A printed card per deck, so every tile draws a face rather than a back. */
const cards = pods.DECKS.map((deck) => [
  ["card", deck.commanders[0]],
  cardResponse({ id: deck.commanders[0], name: deck.commander_names[0] }),
]);

const meta = {
  title: "Lobby/DeckCatalog",
  component: DeckCatalog,
  args: {
    decks: pods.DECKS,
    forSeat: 0,
    forWhom: "You",
    chosen: null,
    onPick: fn(),
    onDossier: fn(),
    onClose: fn(),
    onImported: fn(),
  },
  parameters: { automtg: { mount: "screen", query: cards } },
} satisfies Meta<typeof DeckCatalog>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ForSeat: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("deck-catalog");
    // One tile per deck, each reachable by its own id.
    for (const deck of pods.DECKS) {
      expect(canvasElement.querySelector(`[data-testid="deck-${deck.id}"]`)).not.toBeNull();
    }
  },
};

/** Browsing rather than choosing: no seat, so nothing is being set. */
export const Browsing: Story = {
  args: { forSeat: null, forWhom: "" },
};

/** The deck this seat already holds carries the tick. */
export const Chosen: Story = {
  args: { chosen: "aesi" },
};

/**
 * An imported deck sits in the same grid as the precons.
 *
 * It has no tags and a `simplified` count, and the catalogue draws that honestly
 * rather than padding it out to look like the others.
 */
export const WithImportedDeck: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Zada Storm");
  },
};

/**
 * The card is the control.
 *
 * `deck-{id}` is the tile; the thing that takes the click is the card inside it,
 * which is the whole design -- there is no "Choose" button beside a list.
 */
export const PickDeck: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const tile = await canvas.findByTestId("deck-edgar");
    await userEvent.click(tile.querySelector('[role="button"]') as HTMLElement);
    expect(args.onPick).toHaveBeenCalledWith("edgar");
  },
};

/** The info button opens the dossier rather than taking the deck. */
export const OpenDossier: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByTestId("deck-edgar-info"));
    expect(args.onDossier).toHaveBeenCalledWith("edgar");
    expect(
      args.onPick,
      "opening the dossier must not also take the deck",
    ).not.toHaveBeenCalled();
  },
};

export const Close: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByTestId("deck-catalog-close"));
    expect(args.onClose).toHaveBeenCalled();
  },
};

/** Escape closes it too, which is the only exit a keyboard has. */
export const EscapeCloses: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("deck-catalog");
    await userEvent.keyboard("{Escape}");
    expect(args.onClose).toHaveBeenCalled();
  },
};
