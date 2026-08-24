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
    onDelete: fn(),
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
    // `deck-{id}-take` rather than a `[role=button]` inside `deck-{id}`: the
    // card is the control, and a control the ring has to be able to name needs
    // an id of its own -- see the header.
    await userEvent.click(await canvas.findByTestId("deck-edgar-take"));
    expect(args.onPick).toHaveBeenCalledWith("edgar");
  },
};

/**
 * THE RING OPENS ON A DECK, NOT ON THE WAY OUT.
 *
 * `resolveCursor` falls back to the first stop of whatever surface is on top,
 * which here is the ✕ -- so opening the catalogue with a pad put the ring on
 * the control that leaves the screen the player had just asked for. One line in
 * a layout effect fixes it, and this is what says so.
 */
export const RingOpensOnADeck: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("deck-catalog");
    const ringed = canvasElement.querySelector("[data-cursor]");
    expect(ringed?.getAttribute("data-testid")).toBe(`deck-${pods.DECKS[0].id}-take`);
  },
};

/**
 * ...and on the deck you already hold, when you hold one.
 *
 * "Change my deck" and "choose a deck" are the same control and only one of
 * them starts from nothing; landing on the current pick is what makes the
 * second press a comparison rather than a search.
 */
export const RingOpensOnTheDeckYouHold: Story = {
  args: { chosen: "edgar" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("deck-catalog");
    expect(canvasElement.querySelector("[data-cursor]")?.getAttribute("data-testid")).toBe(
      "deck-edgar-take",
    );
  },
};

/**
 * The grid scrolls, and a deck past the fold is still somewhere the ring can go.
 *
 * `stops.ts:onScreen` used to drop any stop an ancestor had clipped, which is
 * right for the board's zero-height opponent lanes and wrong for a scroller: a
 * deck eleven rows down was not a stop at all, so Down did nothing and the
 * catalogue ended at the fold. `cursor.ts:keepInView` brings the box along on
 * arrival -- and does the arithmetic itself rather than calling
 * `scrollIntoView`, which would also scroll the `overflow: hidden` room and
 * take the header off the top of the screen.
 */
export const TheGridScrolls: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("deck-catalog");
    const body = canvasElement.querySelector(".shelf__body") as HTMLElement;
    expect(getComputedStyle(body).overflowY).toBe("auto");
    // And the room around it never scrolls, whatever the grid does.
    const room = canvasElement.querySelector(".shelf") as HTMLElement;
    expect(getComputedStyle(room).overflow).toBe("hidden");
    expect(room.scrollTop).toBe(0);
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

/**
 * Only an import can be thrown away.
 *
 * A precon ships with the engine -- the server refuses to delete one -- so its
 * tile carries no ✕ at all, rather than one that explains itself after the click.
 */
export const OnlyImportsCanBeRemoved: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("deck-mine-remove");
    expect(canvas.queryByTestId("deck-aesi-remove")).toBeNull();
    expect(canvas.queryByTestId("deck-edgar-remove")).toBeNull();
  },
};

/** The ✕ asks first. One click removes nothing. */
export const RemoveAsksFirst: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByTestId("deck-mine-remove"));
    await canvas.findByTestId("deck-mine-remove-confirm");
    expect(args.onDelete, "the ✕ alone must not delete").not.toHaveBeenCalled();

    await userEvent.click(canvas.getByTestId("deck-mine-remove-yes"));
    expect(args.onDelete).toHaveBeenCalledWith("mine");
    expect(args.onPick, "removing a deck must not also take it").not.toHaveBeenCalled();
  },
};

/** Cancel puts the ✕ back and leaves the deck alone. */
export const RemoveCanBeCancelled: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByTestId("deck-mine-remove"));
    await userEvent.click(await canvas.findByTestId("deck-mine-remove-no"));
    await canvas.findByTestId("deck-mine-remove");
    expect(args.onDelete).not.toHaveBeenCalled();
  },
};

/**
 * A deck somebody at the table has taken keeps its tile and loses its ✕.
 *
 * Deleting it would leave that seat naming a deck the server no longer has --
 * `PodRegistry.start` catches that and refuses to deal, which is a dead end
 * rather than a crash, and a dead end is still worth not walking into.
 */
export const TakenDecksKeepTheirTile: Story = {
  args: { inUse: ["mine"] },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("deck-mine");
    expect(canvas.queryByTestId("deck-mine-remove")).toBeNull();
  },
};
