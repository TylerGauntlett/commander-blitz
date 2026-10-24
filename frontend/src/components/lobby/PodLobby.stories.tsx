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
    onUpdateSeat: fn(),
    onAdminSeat: fn(),
    onSetSeatDeck: fn(),
    onStart: fn(),
    onLeave: fn(),
    onDecksChanged: fn(),
    onStarDeck: fn(),
    ...overrides,
  };
}

/**
 * The four plates are one row, not four stacks.
 *
 * A plate is read ACROSS as much as down: whose seat, which deck, what colours.
 * That only works if the same row is at the same height in all four chairs, and
 * it was not -- your own chair carries a name *field* where the others carry a
 * label, and a field is the taller box. Every row under it inherited the
 * difference, so the deck names, the mana and the buttons all stepped down by a
 * seat. The rows are pinned in `styles/pod.css` (`--who-h`, `--deck-h`,
 * `--act-h`); this is what says so, for whichever pod calls it.
 */
function expectPlateRowsLineUp(canvasElement: HTMLElement): void {
  const tops = (selector: string) =>
    [...canvasElement.querySelectorAll<HTMLElement>(selector)].map((el) =>
      Math.round(el.getBoundingClientRect().top),
    );
  // Every chair has a name line whatever is in it, so this is also the check
  // that the selectors below are still finding anything at all.
  expect(tops(".chair .chair__who").length).toBe(4);
  for (const row of [".chair__who", ".chair__deck", ".chair__act"]) {
    const found = tops(`.chair ${row}`);
    expect(new Set(found).size, `${row} tops: ${found.join(", ")}`).toBeLessThanOrEqual(1);
  }
  // The name itself, not merely the box around it: a field and a label of the
  // same height whose text sits at different depths is the same defect.
  const names = [
    ...canvasElement.querySelectorAll<HTMLElement>(".chair__field, .chair__name"),
  ].map((el) => Math.round(el.getBoundingClientRect().top));
  expect(new Set(names).size, `name tops: ${names.join(", ")}`).toBeLessThanOrEqual(1);
}

const meta = {
  title: "Lobby/PodLobby",
  component: PodLobby,
  parameters: {
    commanderblitz: {
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
    // The denominator is the filled seats, not four. The words that used to
    // sit in front of it -- "Cards face up" -- are off the screen now and live
    // on the `aria-label`, which is the only reader they were ever for.
    expect(track.textContent?.replace(/\s+/g, " ")).toContain("/3");
    expect(track.getAttribute("aria-label")).toContain("of 3");
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

/**
 * NOTHING ON THIS SCREEN IS TYPED INTO.
 *
 * Two fields went, for the same reason from opposite ends. The host-only
 * "Seed" box was a debugging tool standing between a player and the Deal
 * button; the seat-name box cost a virtual keyboard and about twenty presses to
 * replace a name the server already writes. Between them the pod becomes the
 * first screen in the app with nothing on it a ring can get stuck in -- and
 * that is worth an assertion of its own, because the next field somebody adds
 * here will look perfectly reasonable.
 *
 * The specs pin the shuffle through `window.__COMMANDERBLITZ_SEED` instead; see
 * `e2e/helpers.ts:pinSeed`.
 */
export const NothingToTypeInto: Story = {
  args: lobby(pods.ready()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("ready-track");
    expect(canvas.queryByLabelText("Seed")).toBeNull();
    expect(canvas.queryByTestId("your-name")).toBeNull();
    expect(canvasElement.querySelectorAll("input, textarea").length).toBe(0);
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
 * The floors are met by `pod.css` itself rather than by `handheld.css`'s
 * override list, which is the whole point of the new class names: every control
 * here is authored at 44px and every string at `max(16px, ...)`, so there is
 * nothing for a later sheet to have to repair and nothing that can drift from
 * it. This asserts both, on the layout where they bite.
 */
export const PlatesLineUpHandheld: Story = {
  args: lobby(pods.filling()),
  globals: { viewport: { value: "deck" } },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    await within(canvasElement).findByTestId("ready-track");
    expectPlateRowsLineUp(canvasElement);

    for (const control of canvasElement.querySelectorAll<HTMLElement>(
      ".chair button, .chair input, .pod__rail button, .pod__bar button",
    )) {
      const box = control.getBoundingClientRect();
      if (box.width === 0 && box.height === 0) continue;
      expect(
        Math.round(box.height),
        `${control.dataset.testid ?? control.textContent} is under the hit floor`,
      ).toBeGreaterThanOrEqual(44);
      expect(Number.parseFloat(getComputedStyle(control).fontSize)).toBeGreaterThanOrEqual(16);
    }
  },
};

/**
 * THE POD STANDS IN THE SAME ROOM AS THE FRONT DOOR.
 *
 * This is the whole reason the screen was rebuilt, so it is worth an assertion
 * rather than a screenshot: the hall, the floor sigil, the pool of light and
 * the motes are `Room`'s, and the pod is one of three screens standing in it.
 * Pressing PLAY on a menu that looks like a game and landing on a grey panel is
 * not experienced as "one screen has had its pass" -- it is experienced as the
 * game being over a second after it started.
 */
export const StandsInTheRoom: Story = {
  args: lobby(pods.filling()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const pod = await canvas.findByTestId("new-game");
    expect(pod.classList.contains("room")).toBe(true);
    expect(pod.querySelector(".room__ground")).not.toBeNull();
    expect(pod.querySelector(".room__floor")).not.toBeNull();
    expect(pod.querySelectorAll(".mote").length).toBe(16);
    // And it is lit, which is what carries the room's colour into the sigil,
    // the motes and every selected card's glow.
    expect(pod.style.getPropertyValue("--lit")).toBeTruthy();
  },
};

/**
 * ONE GOLD CONTROL PER SCREEN.
 *
 * `room.css` offers three tiers and no more -- `.key`, `.key--commit`,
 * `.key--quiet` -- because the shipped pod had five button classes doing four
 * jobs, and a screen with five button weights has told the player nothing about
 * which one to press. Dealing is the thing this screen exists for, so dealing
 * is the gold one and nothing else is.
 */
export const OneCommitControl: Story = {
  args: lobby(pods.ready()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("start-game");
    const gold = canvasElement.querySelectorAll(".key--commit");
    expect(gold.length).toBe(1);
    expect((gold[0] as HTMLElement).dataset.testid).toBe("start-game");
    // Every other control on the screen is one of the other two tiers, so
    // nothing is styled by hand next to them.
    for (const control of canvasElement.querySelectorAll(
      ".pod__bar button, .pod__rail button",
    )) {
      expect(control.classList.contains("key"), control.textContent ?? "").toBe(true);
    }
  },
};

/**
 * The row of chairs owns the screen, and the caption above it is gone.
 *
 * It said "The pod", and beside it "A card turns face up when its seat picks a
 * deck, and stamps when the seat locks in" -- a rule the screen demonstrates
 * the moment anybody touches it, set in the widest line of text in the app, 42
 * vertical pixels the row needed more on a 7-inch panel.
 */
export const NoCaptionAboveTheRow: Story = {
  args: lobby(pods.filling()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("ready-track");
    expect(canvas.queryByText(/A card turns face up/)).toBeNull();
    expect(canvasElement.querySelector(".tablewrap")).toBeNull();
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
