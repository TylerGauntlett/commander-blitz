/**
 * The play-by-play.
 *
 * Events carry the snake_case card id, not the printed name, so the ticker needs
 * the lookup `useGame` harvests from every zone it sees -- otherwise the log
 * reads "sol_ring". `NoNameLookup` poses the fallback deliberately.
 *
 * Mounted in the log overlay, which is where the log lives at every size now.
 * It used to have a permanent 232px column on a desktop; it is reference you
 * consult rather than something you watch, and it comes up on `View`.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent, within } from "storybook/test";
import { useUiStore } from "../../state/uiStore";
import { expectHandheldFloors } from "../../testing/asserts";
import * as scenarios from "../../testing/scenarios";
import { EventTicker } from "./EventTicker";

const state = scenarios.earlyBoard().state;
const events = scenarios.mixedLog();

/** The map `useGame` builds by watching every zone go past. */
const names: Record<string, string> = {
  forest: "Forest",
  thragtusk: "Thragtusk",
  grizzly_bears: "Grizzly Bears",
  kraken_token: "Kraken",
};

const meta = {
  title: "Game/EventTicker",
  component: EventTicker,
  parameters: { automtg: { mount: "logOverlay" } },
} satisfies Meta<typeof EventTicker>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = {
  args: { state, events: [] },
};

export const MixedLog: Story = {
  args: { state, events, cardName: (id: string) => names[id] },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    // Printed names, not ids -- the same lookup the narration uses, so the log
    // and the beats cannot disagree about what a card is called. Thragtusk
    // appears twice: it is cast, and then countered.
    expect(await canvas.findAllByText(/Thragtusk/)).toHaveLength(2);
    expect(canvasElement.textContent, "an id leaked into the log").not.toMatch(/[a-z]+_[a-z]+/);
  },
};

/** No lookup: `prettyCardName` is the fallback, and must still be readable. */
export const NoNameLookup: Story = {
  args: { state, events },
};

/** Collapsed. The log is a rail that gets in the way when you are not reading it. */
export const LogClosed: Story = {
  args: { state, events, cardName: (id: string) => names[id] },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findAllByText(/Thragtusk/);
    expect(useUiStore.getState().logOpen).toBe(true);

    await userEvent.click(canvasElement.querySelector(".rail__title") as HTMLElement);
    expect(useUiStore.getState().logOpen).toBe(false);
  },
};

/** A long game: the ticker keeps a window and follows the tail. */
export const LongLog: Story = {
  args: {
    state,
    events: Array.from({ length: 60 }, (_, i) => events[i % events.length]),
    cardName: (id: string) => names[id],
  },
};

/** The log overlay on a Deck: 16px lines, a 44px title button. */
export const MixedLogHandheld: Story = {
  args: { state, events, cardName: (id: string) => names[id] },
  globals: { handheld: "on" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findAllByText(/Thragtusk/);
    expectHandheldFloors(canvasElement);
  },
};
