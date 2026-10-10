/**
 * The front door: three cards, and Play is the one it opens on.
 *
 * Mounted on a bare `screen` rather than `screenCenter`, which is what the route
 * does: `.screen--center`'s 24px of padding would put the stage scale at 0.94
 * and shrink the row off the numbers the mockup round measured.
 *
 * Two ways in -- make a pod or join one by code -- and a third card that is not
 * a way in at all: Settings, where a Steam Deck gets told it is a Steam Deck. An
 * invite link fills the code in for you *and opens the hold it lives in*. That
 * prefill is read once at boot and deliberately not synced afterwards: an effect
 * that pushed it in later would arrive after the field had mounted empty, and
 * would fight anybody typing.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { expectHandheldFloors, settled } from "../../testing/asserts";
import { HomeScreen } from "./HomeScreen";

const meta = {
  title: "Lobby/HomeScreen",
  component: HomeScreen,
  parameters: { commanderblitz: { mount: "screen" } },
  args: {
    deckCount: 4,
    busy: false,
    error: null,
    onCreate: fn(),
    onJoin: fn(),
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

/**
 * THE WAY OUT IS A CONTROL, NOT A LEGEND.
 *
 * It was a `<p>` carrying the B glyph and the word Back -- a hint, in the shape
 * of a button, in the place a button goes. Clicking it did nothing; a ring
 * could not reach it at all, because a paragraph is not a stop. So somebody
 * walking the hold with a pad found two stops, neither of them the exit, and
 * the one thing on screen that looked like it.
 *
 * Escape and B still close the hold and always did -- that is the half that
 * worked, and it is why the paragraph survived review. Every overlay in this
 * client owes three ways out: the control, outside the panel, and Escape. This
 * is the one you can point at.
 */
export const TheHoldsWayOutIsPressable: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByTestId("join-pod"));
    await canvas.findByTestId("join-hold");

    const back = await canvas.findByTestId("join-back");
    expect(back.tagName).toBe("BUTTON");
    // At the hit floor, because a Steam Deck has a touchscreen and this is one
    // of the two controls a finger goes for in this panel.
    expect(Math.round(back.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);

    await userEvent.click(back);
    expect(canvas.queryByTestId("join-hold")).toBeNull();
  },
};

/** Settings selected, so the row's other stacked state is reviewable too. */
export const OnSettings: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    // Focus, not a click: pressing this card opens the hold over the row, and
    // what this story is for is the row with an END card selected.
    (await canvas.findByTestId("open-settings")).focus();
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

/**
 * The Settings hold, which is where a Steam Deck gets told it is a Steam Deck.
 *
 * The card exists because the control scheme cannot always be inferred: in
 * gaming mode Steam hands the browser a KEYBOARD, so the app's own signals say
 * "keyboard" while the player is holding a controller. This is the surface that
 * lets them say otherwise, and the one that explains why the pad was not found.
 */
export const SettingsHold: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByTestId("open-settings"));
    const panel = await canvas.findByTestId("controller-panel");
    expect(panel).toBeVisible();

    // The four schemes are native buttons, so the ring reaches them for free --
    // a control-scheme setting you need a working control scheme to reach is
    // furniture.
    for (const id of ["auto", "pad", "keyboard", "mouse"]) {
      expect(await canvas.findByTestId(`scheme-${id}`)).toBeVisible();
    }

    // Storybook runs without a gamepad, which is the case worth drawing: the
    // panel has to name the causes rather than just report the symptom.
    expect(await canvas.findByTestId("controller-status")).toBeVisible();
  },
};

/**
 * THE DESKTOP'S THIRD CARD IS ONLINE.
 *
 * On the Steam Deck the game runs from a server on the device and a pod with
 * other people lives on the hosted site, so Join becomes the way there. With no
 * connection the card stays in the row -- removing it would move Play off the
 * middle -- dimmed, still a stop, and pressing it says why.
 */
export const DesktopOffline: Story = {
  args: { mode: "desktop", online: false, onPlayOnline: fn() },
  globals: { handheld: "on" },
  tags: ["handheld"],
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const card = await canvas.findByTestId("join-pod");
    expect(card).toHaveTextContent("Online");
    expect(card).toHaveAttribute("aria-disabled", "true");
    // One click selects the card, the second presses it.
    await userEvent.click(card);
    await userEvent.click(card);
    await canvas.findByTestId("offline-note");
    expect(canvas.queryByTestId("join-hold")).toBeNull();
    expect(args.onPlayOnline).not.toHaveBeenCalled();
    await settled(canvasElement);
    expectHandheldFloors(canvasElement);
  },
};

/** ...and with a connection, the hold takes a code or goes with none. */
export const DesktopOnline: Story = {
  args: { mode: "desktop", online: true, onPlayOnline: fn() },
  globals: { handheld: "on" },
  tags: ["handheld"],
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const card = await canvas.findByTestId("join-pod");
    await userEvent.click(card);
    await userEvent.click(card);
    await canvas.findByTestId("join-hold");
    const go = await canvas.findByTestId("play-online");
    expect(Math.round(go.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    await userEvent.click(go);
    expect(args.onPlayOnline).toHaveBeenCalledWith();
    expect(args.onJoin).not.toHaveBeenCalled();
  },
};

/** The front door on a Deck: three cards, each a target. */
export const FreshHandheld: Story = {
  args: Fresh.args,
  globals: { handheld: "on" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    await settled(canvasElement);
    expectHandheldFloors(canvasElement);
  },
};
