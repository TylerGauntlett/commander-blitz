/**
 * The deck browser, where the card *is* the control.
 *
 * There is no list with a button beside it: you pick a deck by clicking its
 * commander. That makes the catalogue a grid of real faces, which is why it
 * needs its card queries seeded to render on first paint.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, waitFor, within } from "storybook/test";
import { expectFontFloor, expectHandheldFloors, settled } from "../../testing/asserts";
import { cardResponse } from "../../testing/fixtures";
import * as pods from "../../testing/pods";
import { FAVORITES, PRECONS, shelfCards, UPCOMING, YOURS } from "../../testing/shelf";
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
    onStar: fn(),
  },
  parameters: { commanderblitz: { mount: "screen", query: cards } },
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
 * An imported deck sits on the same shelf as the shipped decks, in a run of
 * its own under All.
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
 * An import the desktop build has not finished fetching the art for.
 *
 * Only that tile says so, and only on the desktop: a deck file there carries
 * `complete`, and the next launch with a connection finishes it (ADR 0022).
 */
export const ArtStillToFetch: Story = {
  globals: { handheld: "on" },
  tags: ["handheld"],
  args: {
    decks: pods.DECKS.map((deck) => (deck.id === "mine" ? { ...deck, complete: false } : deck)),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const badge = await canvas.findByTestId("deck-mine-incomplete");
    expect(badge.getAttribute("aria-label")).toMatch(/not on this device/);
    expect(canvas.queryByTestId("deck-aesi-incomplete")).toBeNull();
    expectFontFloor(canvasElement);
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

/**
 * Escape closes it too, and so does `B` -- which is the same thing.
 *
 * `buttons.ts` maps Escape onto the pad's `b`, so both arrive through
 * `useDismiss` one frame later rather than through a `window` listener of this
 * component's own. `waitFor` is that frame; see `input/useDismiss.ts` for why
 * the raw-key path had to go.
 */
export const EscapeCloses: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("deck-catalog");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(args.onClose).toHaveBeenCalled());
  },
};

/**
 * B CLOSES IT, AND THE FOOTER HAS BEEN PROMISING THAT SINCE THE FIRST DRAFT.
 *
 * Nothing was listening. `tests/hintsBound.test.ts` asks only whether a button
 * is bound *somewhere* in the app, so a hint drawn on a surface that binds it
 * nowhere passes -- and this surface drew `B — Back` and bound nothing. A
 * player on a pad pressed the advertised button, the game ignored it, and their
 * controller layout's own idea of Back took over instead: on a Steam Deck a
 * history step, which from a pod's address is the front door. Backing out of
 * the deck catalogue dropped them out of the pod.
 *
 * `k` rather than `{Escape}` on purpose: it is `B` in `KEYS` and nothing else,
 * so this exercises the pad intent rather than a key an overlay might happen to
 * be listening for.
 */
export const BackCloses: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("deck-catalog");
    await userEvent.keyboard("k");
    await waitFor(() => expect(args.onClose).toHaveBeenCalled());
  },
};

/**
 * Only an import can be thrown away.
 *
 * A shipped deck comes with the engine -- the server refuses to delete one -- so
 * its tile carries no ✕ at all, rather than one that explains itself after the
 * click.
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

/* ------------------------------------------------------------------ */
/* The shelf's segments (ADR 0024)                                     */
/* ------------------------------------------------------------------ */

/** Every deck a full shelf has: two releases of precons, the twelve, yours. */
const SHELF = [...PRECONS, ...FAVORITES, ...YOURS];

/** The ids of the tiles in one container, in the order they are drawn. */
function tileIds(root: Element): string[] {
  return [...root.querySelectorAll<HTMLElement>(".tile")].map(
    (tile) => tile.dataset.testid?.replace(/^deck-/, "") ?? "",
  );
}

/** The named runs on the shelf, in order. */
function regionNames(root: HTMLElement): string[] {
  return within(root)
    .queryAllByRole("region")
    .map((region) => region.getAttribute("aria-label") ?? "");
}

/**
 * The four segments, in the order the shelf promises them. Each is a word that
 * is true of what it holds: Precons are what Wizards sold, Favorites what the
 * maintainer ships, Yours what you imported.
 */
async function segments(canvasElement: HTMLElement): Promise<void> {
  const canvas = within(canvasElement);
  await canvas.findByTestId("deck-catalog");
  const names = [...canvasElement.querySelectorAll(".seg__b")].map((b) => b.textContent);
  expect(names).toEqual(["All", "Precons", "Favorites", "Yours"]);
}

/**
 * THE FAVORITES ARE THE TWELVE, and nothing else.
 *
 * The lists the maintainer likes, under the word that is true of them. Under
 * a segment of its own one run needs no header, and no favorite names an
 * archetype yet, so there is no archetype control to walk past.
 */
export const Favorites: Story = {
  args: { decks: SHELF },
  globals: { handheld: "on" },
  tags: ["handheld"],
  parameters: { commanderblitz: { mount: "screen", query: shelfCards(SHELF) } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await segments(canvasElement);
    await userEvent.click(canvas.getByTestId("source-favorite"));

    const body = canvasElement.querySelector(".shelf__body") as HTMLElement;
    await waitFor(() => expect(tileIds(body)).toHaveLength(FAVORITES.length));
    expect(new Set(tileIds(body))).toEqual(new Set(FAVORITES.map((deck) => deck.id)));
    expect(canvas.getByTestId("deck-count")).toHaveTextContent(
      `${FAVORITES.length}/${SHELF.length}`,
    );
    expect(regionNames(body), "one run, and the segment already names it").toEqual([]);
    expect(canvas.queryByTestId("deck-archetype")).toBeNull();
    // A shipped deck carries no star: it is everybody's shelf.
    expect(body.querySelector(".tile__star")).toBeNull();

    await settled(canvasElement);
    expectHandheldFloors(canvasElement);
  },
};

/**
 * PRECONS RUN BY RELEASE, NEWEST FIRST.
 *
 * The fixture lists the older release first, so finding Foundations on top is
 * `groupDecks` ordering the runs and not the fixture. Each run is a region
 * named for its product, which is what a screen reader jumps between and what
 * breaks a pad's walk down the grid into sets.
 */
export const Precons: Story = {
  args: { decks: SHELF },
  globals: { handheld: "on" },
  tags: ["handheld"],
  parameters: { commanderblitz: { mount: "screen", query: shelfCards(SHELF) } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await segments(canvasElement);
    await userEvent.click(canvas.getByTestId("source-precon"));

    const body = canvasElement.querySelector(".shelf__body") as HTMLElement;
    await waitFor(() =>
      expect(regionNames(body)).toEqual(["Foundations Commander", "Duskmourn Commander"]),
    );
    const [newest, older] = within(body).getAllByRole("region");
    expect(within(newest).getByRole("heading")).toHaveTextContent("Foundations Commander");
    expect(tileIds(newest)).toEqual(["fdc_calling_all_angels", "fdc_wild_hunt"]);
    expect(tileIds(older)).toEqual(["dsc_death_toll", "dsc_endless_punishment"]);
    expect(tileIds(body), "nothing but precons in the segment").toHaveLength(PRECONS.length);
    // A header is type, not a place the ring can stop.
    expect(newest.querySelector("h2")?.hasAttribute("data-stop")).toBe(false);

    await settled(canvasElement);
    expectHandheldFloors(canvasElement);

    // These precons name archetypes, so the filter is drawn; one press narrows
    // to the first of them, and the run it empties goes with it.
    const archetype = canvas.getByTestId("deck-archetype");
    expect(archetype).toHaveAttribute("aria-label", "Archetype: Any");
    await userEvent.click(archetype);
    expect(archetype).toHaveAttribute("aria-label", "Archetype: Aristocrats");
    await waitFor(() => expect(regionNames(body)).toEqual(["Duskmourn Commander"]));
    expect(tileIds(body)).toEqual(["dsc_death_toll"]);
    expectHandheldFloors(canvasElement);
  },
};

/**
 * A STAR PINS AN IMPORT TO THE TOP OF YOURS.
 *
 * Yuriko sorts last by name and is drawn first, because it is starred. The
 * star is one toggle per import and nowhere else. Pressing one asks the server
 * and changes nothing by itself: the tile redraws from the deck list the
 * answer brings back, and this story sends none, so it stays as it was.
 */
export const Yours: Story = {
  args: { decks: SHELF },
  globals: { handheld: "on" },
  tags: ["handheld"],
  parameters: { commanderblitz: { mount: "screen", query: shelfCards(SHELF) } },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await segments(canvasElement);
    await userEvent.click(canvas.getByTestId("source-moxfield"));

    const body = canvasElement.querySelector(".shelf__body") as HTMLElement;
    await waitFor(() => expect(tileIds(body)).toHaveLength(YOURS.length));
    expect(tileIds(body)).toEqual(["mox_yuriko", "mox_alela", "mox_krenko"]);
    expect(regionNames(body)).toEqual([]);

    for (const deck of YOURS) {
      const stars = body.querySelectorAll(`[data-testid="deck-${deck.id}-star"]`);
      expect(stars, `${deck.id} has exactly one star`).toHaveLength(1);
      expect(stars[0]).toHaveAttribute("aria-pressed", String(deck.starred));
    }

    const star = canvas.getByTestId("deck-mox_alela-star");
    await userEvent.click(star);
    expect(args.onStar).toHaveBeenCalledWith("mox_alela", true);
    expect(args.onPick, "a star must not also take the deck").not.toHaveBeenCalled();
    expect(star, "no answer came back, so nothing moved").toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(tileIds(body)[0]).toBe("mox_yuriko");

    await userEvent.click(canvas.getByTestId("deck-mox_yuriko-star"));
    expect(args.onStar).toHaveBeenCalledWith("mox_yuriko", false);

    await settled(canvasElement);
    expectHandheldFloors(canvasElement);
  },
};

/** All of it at once: every run under its own header, the precons first. */
export const AllRuns: Story = {
  args: { decks: SHELF },
  globals: { handheld: "on" },
  tags: ["handheld"],
  parameters: { commanderblitz: { mount: "screen", query: shelfCards(SHELF) } },
  play: async ({ canvasElement }) => {
    await segments(canvasElement);
    const body = canvasElement.querySelector(".shelf__body") as HTMLElement;
    expect(regionNames(body)).toEqual([
      "Foundations Commander",
      "Duskmourn Commander",
      "Favorites",
      "Yours",
    ]);
    // The ring opens on the first deck of the first run.
    expect(canvasElement.querySelector("[data-cursor]")?.getAttribute("data-testid")).toBe(
      "deck-fdc_calling_all_angels-take",
    );
    await settled(canvasElement);
    expectHandheldFloors(canvasElement);
  },
};

/**
 * PRECONS WITH COMING-SOON SHELLS.
 *
 * The whole catalogue, the playable and the not yet. A shell joins its
 * release's run after the decks that can be dealt, and a release with nothing
 * playable is a run of shells alone, placed by its date. A shell is not a
 * control: no role, no tab stop, nowhere for the ring to land, and a press
 * on it takes nothing. A colour filter hides every shell, since a shell has
 * no identity to match.
 */
export const PreconsWithComingSoonShells: Story = {
  args: { decks: SHELF, upcoming: UPCOMING },
  globals: { handheld: "on" },
  tags: ["handheld"],
  parameters: { commanderblitz: { mount: "screen", query: shelfCards(SHELF) } },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await segments(canvasElement);
    await userEvent.click(canvas.getByTestId("source-precon"));

    const body = canvasElement.querySelector(".shelf__body") as HTMLElement;
    await waitFor(() =>
      expect(regionNames(body)).toEqual([
        "Foundations Commander",
        "Bloomburrow Commander",
        "Duskmourn Commander",
      ]),
    );
    const [foundations, bloomburrow] = within(body).getAllByRole("region");
    // Playable first, then the shell, in one grid.
    const order = [...foundations.querySelectorAll<HTMLElement>(".tile, .shell")].map(
      (el) => el.dataset.testid,
    );
    expect(order).toEqual([
      "deck-fdc_calling_all_angels",
      "deck-fdc_wild_hunt",
      "shell-fdc_grave_danger",
    ]);
    expect(tileIds(bloomburrow), "nothing playable in Bloomburrow").toEqual([]);
    expect(bloomburrow.querySelectorAll(".shell")).toHaveLength(2);

    const shell = canvas.getByTestId("shell-fdc_grave_danger");
    expect(shell).toHaveTextContent("Coming soon");
    expect(shell).toHaveTextContent("Grave Danger");
    expect(shell).toHaveTextContent("Ghoul Lord of the Crypt");
    expect(shell.querySelector("img.shell__art")).not.toBeNull();
    // A shell without a printing draws a plain plate, not a broken image.
    expect(canvas.getByTestId("shell-blc_family_matters").querySelector("img")).toBeNull();

    // Not a control, anywhere inside it.
    for (const el of body.querySelectorAll<HTMLElement>(".shell, .shell *")) {
      expect(el.getAttribute("role"), "a shell is not a control").toBeNull();
      expect(el.hasAttribute("tabindex")).toBe(false);
      expect(el.hasAttribute("data-stop")).toBe(false);
      expect(el.tagName).not.toBe("BUTTON");
    }
    await userEvent.click(shell);
    expect(args.onPick).not.toHaveBeenCalled();
    expect(args.onDossier).not.toHaveBeenCalled();

    await settled(canvasElement);
    expectHandheldFloors(canvasElement);

    // A colour filter hides the shells, and the run they alone made goes too.
    await userEvent.click(canvas.getByTestId("colour-W"));
    await waitFor(() => expect(body.querySelectorAll(".shell")).toHaveLength(0));
    expect(regionNames(body)).toEqual(["Foundations Commander"]);
  },
};
