/**
 * The pod screen: four seats as a hand of cards, and a rail down the side.
 *
 * The states worth posing are the incomplete ones -- who has arrived, who has
 * locked in, and what a guest is allowed to see that the host is not.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { cardResponse } from "../../testing/fixtures";
import * as pods from "../../testing/pods";
import { PodLobby } from "./PodLobby";

function lobby(pod = pods.filling(), overrides = {}) {
  return {
    pod,
    decks: pods.DECKS,
    busy: false,
    starting: false,
    error: null,
    seed: "",
    onSeedChange: fn(),
    onUpdateSeat: fn(),
    onAdminSeat: fn(),
    onSetSeatDeck: fn(),
    onStart: fn(),
    onLeave: fn(),
    onDecksChanged: fn(),
    ...overrides,
  };
}

/**
 * The four plates are one row, not four stacks.
 *
 * A plate is read ACROSS as much as down: whose seat, which deck, what colours.
 * That only works if the same row is at the same height in all four slots, and
 * it was not -- your own chair carries a name *field* where the others carry a
 * label, and a field is the taller box. Every row under it inherited the
 * difference, so the deck names, the mana and the buttons all stepped down by a
 * seat. The rows are pinned to one height in `styles/lobby.css`; this is what
 * says so, for whichever pod the story it is called from poses.
 */
function expectPlateRowsLineUp(canvasElement: HTMLElement): void {
  const tops = (selector: string) =>
    [...canvasElement.querySelectorAll<HTMLElement>(selector)].map((el) =>
      Math.round(el.getBoundingClientRect().top),
    );
  // Every slot has a name line whatever is in it, so this is also the check
  // that the selectors below are still finding anything at all.
  expect(tops(".slot .plate__who").length).toBe(4);
  for (const row of [".plate__who", ".plate__deck", ".plate__meta", ".plate__acts"]) {
    const found = tops(`.slot ${row}`);
    expect(new Set(found).size, `${row} tops: ${found.join(", ")}`).toBeLessThanOrEqual(1);
  }
  // The name itself, not merely the box around it: a field and a label of the
  // same height whose text sits at different depths is the same defect.
  const names = [...canvasElement.querySelectorAll<HTMLElement>(".plate__name, .plate__n")].map(
    (el) => Math.round(el.getBoundingClientRect().top),
  );
  expect(new Set(names).size, `name tops: ${names.join(", ")}`).toBeLessThanOrEqual(1);
}

const meta = {
  title: "Lobby/PodLobby",
  component: PodLobby,
  parameters: {
    automtg: {
      mount: "screen",
      query: [[["card", "aesi_tyrant_of_gyre_strait"], cardResponse()]],
    },
  },
} satisfies Meta<typeof PodLobby>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Just created: your chair and three empty ones. */
export const EmptyPod: Story = {
  args: lobby(pods.empty()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("ready-track");
    // Three chairs nobody has taken, and they line up with the one you are in.
    expectPlateRowsLineUp(canvasElement);
  },
};

export const Filling: Story = { args: lobby(pods.filling()) };

/**
 * Three players, not four.
 *
 * The ready track counts the seats that are *filled*, so a three-handed pod is
 * not permanently 3/4 done -- a progress bar that can never complete is worse
 * than no progress bar.
 */
export const ThreeHanded: Story = {
  args: lobby(pods.threeHanded()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const track = await canvas.findByTestId("ready-track");
    // The denominator is the filled seats, not four.
    // Whitespace is normalised because the label is typeset with
    // non-breaking spaces.
    expect(track.textContent?.replace(/\s+/g, " ")).toContain("of 3");
  },
};

/** Everybody locked in: dealing is the only thing left to do. */
export const AllReady: Story = {
  args: lobby(pods.ready()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const start = await canvas.findByTestId("start-game");
    expect(start.hasAttribute("disabled")).toBe(false);
    // Four seats all showing the same things: the plainest case, and the one a
    // row height that came from the content would happen to get right anyway.
    expectPlateRowsLineUp(canvasElement);
  },
};

export const StartFlow: Story = {
  args: lobby(pods.ready()),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByTestId("start-game"));
    expect(args.onStart).toHaveBeenCalled();
  },
};

/** The host has dealt; everyone is about to be moved to the table. */
export const Starting: Story = {
  args: lobby(pods.starting(), { starting: true }),
};

/**
 * A guest's view of the same pod.
 *
 * Host controls are hidden rather than disabled, so this is a different screen
 * and not a greyed-out one.
 */
export const GuestView: Story = {
  args: lobby(pods.guestView()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("ready-track");
    expect(canvas.queryByTestId("start-game")).toBeNull();
  },
};

/** A seed makes a game reproducible, which is how a bug report gets repeated. */
export const SeedEntry: Story = {
  args: lobby(pods.ready()),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    // Labelled rather than placeheld: the placeholder is "random", which is what
    // an empty seed means rather than what the field is.
    const field = await canvas.findByLabelText("Seed");
    await userEvent.type(field, "7");
    expect(args.onSeedChange).toHaveBeenCalled();
  },
};

/**
 * The mix that drifted: four seats of four different kinds -- yours, a player
 * who has not locked in, a CPU, and an open chair.
 */
export const PlatesLineUp: Story = {
  args: lobby(pods.filling()),
  play: async ({ canvasElement }) => {
    await within(canvasElement).findByTestId("ready-track");
    expectPlateRowsLineUp(canvasElement);
  },
};

/**
 * The same row, at a Steam Deck's panel -- where it is furthest out.
 *
 * The handheld layout raises every control to a 44px hit floor, and the name
 * field is a control while the label beside it is not. That is a 25px step
 * rather than the desktop's six, and it also caught the details glyph: a
 * `min-height` with no `min-width` turned a 17px circle into a 17x44 pill.
 */
export const PlatesLineUpHandheld: Story = {
  args: lobby(pods.filling()),
  globals: { handheld: "on" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    await within(canvasElement).findByTestId("ready-track");
    expectPlateRowsLineUp(canvasElement);

    /*
     * The target is 44px and the mark is not, which is the only way both the
     * hit floor and a plate the size of a playing card can be right. The circle
     * is `::before`, so it is measured through the cascade rather than through
     * a box -- a pseudo-element has no `getBoundingClientRect`.
     */
    for (const glyph of canvasElement.querySelectorAll<HTMLElement>(".ibtn")) {
      const box = glyph.getBoundingClientRect();
      expect(Math.round(box.width), "the details target is square").toBe(
        Math.round(box.height),
      );
      expect(Math.round(box.width)).toBeGreaterThanOrEqual(44);

      const mark = getComputedStyle(glyph, "::before");
      expect(mark.width, "the drawn circle is round").toBe(mark.height);
      expect(Number.parseFloat(mark.width)).toBeLessThan(30);
    }
  },
};

export const Busy: Story = { args: lobby(pods.filling(), { busy: true }) };

export const WithError: Story = {
  args: lobby(pods.filling(), { error: new Error("That chair was just taken.") }),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/just taken/);
  },
};
