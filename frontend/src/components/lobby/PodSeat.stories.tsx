/**
 * One chair.
 *
 * The chair is the lobby's hidden-information rule made visible: a face-down
 * card is one picture for three different facts -- an empty chair, a chair held
 * for somebody who has not arrived, and a real deck somebody has not revealed
 * yet. They must look similar and must never *test* the same, which is why
 * `CardBack` takes a `testId`.
 *
 * The second property these stories carry is newer and is about the pad rather
 * than about secrecy: **a chair offers at most one button.** It used to offer
 * two, and the second said "Invite a player" on all three empty chairs -- the
 * same words the header carries, three more times, on the screen with the least
 * room for them and one more stop each to walk past.
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
    onClear: fn(),
    onDossier: fn(),
  };
}

const meta = {
  title: "Lobby/PodSeat",
  component: PodSeat,
  parameters: {
    automtg: {
      mount: "podHand",
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

/** Your own chair: the only deck you can see before anybody locks in. */
export const You: Story = {
  args: seat(filling, 0),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("You");
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
 * ONE BUTTON, WHATEVER IS IN THE CHAIR.
 *
 * The count is the assertion, not the label: four chairs used to add up to
 * eight buttons on an empty pod, and a row a thumb has to walk is a row where
 * every extra control is a wrong turn. Inviting is one control in the header;
 * reading a deck is the card itself.
 */
export const AtMostOneButton: Story = {
  args: seat(filling, 0),
  play: async ({ canvasElement }) => {
    for (const index of [0, 1, 2, 3]) {
      const one = filling.seats[index];
      expect(one, `seat ${index} exists`).toBeTruthy();
    }
    const acts = canvasElement.querySelectorAll(".chair__act button");
    expect(acts.length).toBeLessThanOrEqual(1);
  },
};

/**
 * Every control is named, and that is a navigation requirement rather than a
 * testing one.
 *
 * `stopIdOf` falls back to accessible-name-plus-INDEX for a control with no id,
 * so "Add a CPU" in seat 3 was `ui:Add a CPU:9` -- and the moment seat 2 became
 * a CPU the whole list re-indexed, every id changed at once, and the ring fell
 * back to the first control on the screen. A chair has to be the same stop
 * before and after the pod changes under it.
 */
export const EveryControlIsNamed: Story = {
  args: seat(pods.empty(), 1),
  play: async ({ canvasElement }) => {
    const controls = canvasElement.querySelectorAll("button, input");
    expect(controls.length).toBeGreaterThan(0);
    for (const control of controls) {
      expect(
        control.getAttribute("data-testid"),
        `${control.textContent || control.tagName} carries no id`,
      ).toBeTruthy();
    }
  },
};

/**
 * Your own chair before you have chosen says CHOOSE, not SEALED.
 *
 * "Sealed" is what everybody else's unchosen chair says -- "somebody is here
 * and you may not see what they brought". Printing it on your own told you your
 * own deck was being kept from you.
 */
export const YourChairBeforeYouChoose: Story = {
  args: seat(pods.fresh(), 0),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const back = await canvas.findByTestId("card-back");
    expect(back.textContent).toMatch(/Choose/i);
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
    expect(canvasElement.querySelectorAll(".chair__act button").length).toBe(0);
  },
};

/**
 * NOBODY TYPES A NAME, AND THE ABSENCE IS THE POINT.
 *
 * Your chair carried a text field here. Typing into it with a controller is a
 * virtual keyboard, a d-pad and about twenty presses to replace "Player 1" with
 * something nobody at the table needs -- and it was the last text box on the
 * pod, which made it the last place a ring could get stuck. The server names
 * every chair after its seat, so the row still reads as four distinct people.
 */
export const NoNameField: Story = {
  args: seat(filling, 0),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("You");
    expect(canvas.queryByTestId("your-name")).toBeNull();
    expect(canvasElement.querySelectorAll("input").length).toBe(0);
  },
};

/** Everything gated while a request is in flight. */
export const Disabled: Story = {
  args: { ...seat(filling, 0), disabled: true },
};
