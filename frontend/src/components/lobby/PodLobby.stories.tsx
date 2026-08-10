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

const meta = {
  title: "Lobby/PodLobby",
  component: PodLobby,
  parameters: {
    automtg: {
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

export const Busy: Story = { args: lobby(pods.filling(), { busy: true }) };

export const WithError: Story = {
  args: lobby(pods.filling(), { error: new Error("That chair was just taken.") }),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/just taken/);
  },
};
