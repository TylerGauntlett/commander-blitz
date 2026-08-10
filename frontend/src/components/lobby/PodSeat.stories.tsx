/**
 * One chair.
 *
 * The seat is the lobby's hidden-information rule made visible: a face-down card
 * is one picture for three different facts -- an empty chair, a chair held for
 * somebody who has not arrived, and a real deck somebody has not revealed yet.
 * They must look similar and must never *test* the same, which is why `CardBack`
 * takes a `testId`.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { cardResponse } from "../../testing/fixtures";
import * as pods from "../../testing/pods";
import { PodSeat } from "./PodSeat";

const filling = pods.filling();
const guest = pods.guestView();

function seat(pod = filling, index = 0, youAreHost = true) {
  return {
    pod,
    seat: pod.seats[index],
    youAreHost,
    onChooseDeck: fn(),
    onAddCpu: fn(),
    onOpenChair: fn(),
    onClear: fn(),
    onInvite: fn(),
    onDossier: fn(),
    onRename: fn(),
  };
}

const meta = {
  title: "Lobby/PodSeat",
  component: PodSeat,
  parameters: {
    automtg: {
      frame: "bare",
      // Seeded so the commander face is there on first paint rather than
      // resolving a tick later and racing the assertion.
      query: [
        [["card", "aesi_tyrant_of_gyre_strait"], cardResponse()],
        [
          ["card", "edgar_markov"],
          cardResponse({
            id: "edgar_markov",
            name: "Edgar Markov",
            type_line: "Legendary Creature — Vampire Knight",
            mana_cost: "{3}{R}{W}{B}",
            colors: ["B", "R", "W"],
            color_identity: ["B", "R", "W"],
          }),
        ],
      ],
    },
  },
} satisfies Meta<typeof PodSeat>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Your own chair: the only one you may rename, and the only deck you can see. */
export const You: Story = {
  args: seat(filling, 0),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByDisplayValue("You");
  },
};

/**
 * Another human who has not locked in.
 *
 * Their deck is `null` until they do, so this draws a sealed back rather than an
 * empty one -- "somebody is sitting here and you may not see what they brought"
 * is a different fact from "nobody is here".
 */
export const HumanGuestUnlocked: Story = {
  args: seat(filling, 1),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const back = await canvas.findByTestId("card-back");
    expect(back.dataset.tone).toBe("sealed");
  },
};

export const Cpu: Story = { args: seat(filling, 2) };

/** A chair held open for somebody who has not arrived. */
export const OpenChair: Story = {
  args: seat(filling, 3),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const back = await canvas.findByTestId("card-back");
    expect(back.dataset.tone).toBe("open");
  },
};

/** Nobody, and nobody invited. */
export const EmptySeat: Story = {
  args: seat(pods.empty(), 1),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const back = await canvas.findByTestId("card-back");
    expect(back.dataset.tone).toBe("empty");
  },
};

export const LockedAndReady: Story = { args: seat(pods.ready(), 1) };

/** Host controls exist here. */
export const HostControls: Story = {
  args: seat(pods.empty(), 1),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByText(/CPU/i));
    expect(args.onAddCpu).toHaveBeenCalledWith(1);
  },
};

/**
 * The same empty chair, seen by a guest.
 *
 * Host-only controls are *absent*, not disabled -- a greyed-out button invites
 * you to wonder what you did wrong.
 */
export const GuestSeesNoControls: Story = {
  args: seat(guest, 3, false),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(canvas.queryByText(/Add CPU/i)).toBeNull();
  },
};

/** Renaming your own chair. */
export const RenamingYourself: Story = {
  args: seat(filling, 0),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const field = await canvas.findByDisplayValue("You");
    await userEvent.clear(field);
    await userEvent.type(field, "Tyler");
    // A local draft, not a controlled read: the pod re-renders on every
    // long-poll return and a field that reset itself mid-word is unusable.
    expect((field as HTMLInputElement).value).toBe("Tyler");
    await userEvent.tab();
    expect(args.onRename).toHaveBeenCalledWith("Tyler");
  },
};

/** Everything gated while a request is in flight. */
export const Disabled: Story = {
  args: { ...seat(filling, 0), disabled: true },
};
