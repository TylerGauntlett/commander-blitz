/**
 * The front door: three cards, and the middle one is Play.
 *
 * Mounted on a bare `screen` rather than `screenCenter`, which is what the route
 * does: `.screen--center`'s 24px of padding would put the stage scale at 0.94
 * and shrink the row off the numbers the mockup round measured.
 *
 * Two ways in -- make a pod, or join one by code -- and an invite link fills the
 * code in for you *and opens the hold it lives in*. That prefill is read once at
 * boot and deliberately not synced afterwards: an effect that pushed it in later
 * would arrive after the field had mounted empty, and would fight anybody
 * typing.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { HomeScreen } from "./HomeScreen";

const meta = {
  title: "Lobby/HomeScreen",
  component: HomeScreen,
  parameters: { automtg: { mount: "screen" } },
  args: {
    deckCount: 4,
    busy: false,
    error: null,
    onCreate: fn(),
    onJoin: fn(),
    onBrowse: fn(),
  },
} satisfies Meta<typeof HomeScreen>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Fresh: Story = {};

/** Arrived from `?join=CODE`, so the hold is open and the field is filled. */
export const WithInviteCode: Story = {
  args: { initialCode: "GYRE-8412" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByDisplayValue("GYRE-8412");
  },
};

export const CreateFlow: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByTestId("create-pod"));
    expect(args.onCreate).toHaveBeenCalled();
  },
};

export const JoinFlow: Story = {
  args: { initialCode: "GYRE-8412" },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByDisplayValue("GYRE-8412");
    // By id, not by text: there are three "Join"s on this screen now -- the
    // card, the hold's heading, and the confirm -- and only one of them submits.
    await userEvent.click(await canvas.findByTestId("join-go"));
    expect(args.onJoin).toHaveBeenCalledWith("GYRE-8412");
  },
};

/** Pressing the Join card is what opens the hold when no link filled it in. */
export const JoinFromTheCard: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByTestId("join-pod"));
    await canvas.findByTestId("join-hold");
  },
};

/** Decks and Join, so the two stacked states are both reviewable. */
export const OnDecks: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByTestId("browse-decks"));
  },
};

export const Busy: Story = { args: { busy: true } };

export const WithError: Story = {
  args: { error: new Error("No pod with that code.") },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/No pod with that code/);
  },
};

/** No decks at all, which is what a fresh install looks like. */
export const NoDecks: Story = { args: { deckCount: 0 } };
