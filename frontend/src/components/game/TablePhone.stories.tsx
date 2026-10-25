/**
 * The whole board on phones (ADR 0025).
 *
 * Each story names a viewport from `testing/devices.ts` -- the iPhone 15, the
 * Pixel 7 and the iPhone Duo folded, each held both ways -- and the Vitest
 * addon sizes the page to it, so the phone query matches and `styles/phone.css`
 * lays the board out exactly as the device would. `tags: ["phone"]` puts them
 * in the `storybook-phone` project, and every one asserts the phone's own
 * floors (`logic/floors.ts`), that nothing has been pushed out of its region,
 * and that the page does not scroll sideways.
 *
 * What to look at, upright: the opponents are a strip of orbs, the viewer's mat
 * is the board, the hand is a drawer and the action panel is a sheet at the
 * bottom with the commit slab under the thumb. Held sideways, the panel is a
 * rail beside the board.
 *
 * `zoomLock: false` on all of them, for the reason `TableHandheld.stories.tsx`
 * gives: the card floor is a claim about what the solver does with the room.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent, waitFor, within } from "storybook/test";
import { useUiStore } from "../../state/uiStore";
import {
  expectHandheldFloors,
  expectNoSideScroll,
  expectNothingOverflows,
  expectUniqueActionIds,
  expectViewport,
} from "../../testing/asserts";
import { board } from "../../testing/board";
import { viewportById } from "../../testing/devices";
import { action } from "../../testing/fixtures";
import * as scenarios from "../../testing/scenarios";
import { Table } from "./Table";

const meta = {
  title: "Game/Table Phone",
  component: Table,
  parameters: { commanderblitz: { mount: "screen", zoomLock: false } },
  tags: ["phone"],
} satisfies Meta<typeof Table>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Where scrolling IS the phone's design.
 *
 * The viewer's mat is three lanes and an info column at a card a thumb can
 * read; upright there is a strip of the screen for it between the orbs and the
 * drawer, so it scrolls, as a long action list does. The Deck's gate does not
 * get this exemption -- its board fits its panel and must keep fitting.
 */
const PHONE_SCROLLERS = [".play__mine", ".play__mine .mat__side"];

/** The gate every phone story ends on, on the viewport it names. */
async function holds(canvasElement: HTMLElement, viewport: string): Promise<void> {
  const canvas = within(canvasElement);
  await canvas.findByTestId("table");
  const size = viewportById(viewport)?.size;
  expect(size, viewport).toBeDefined();
  if (size) expectViewport(size);
  expect(document.documentElement.getAttribute("data-layout")).toBe("phone");
  expectHandheldFloors(canvasElement);
  expectNothingOverflows(canvasElement, PHONE_SCROLLERS);
  expectUniqueActionIds(canvasElement);
  expectNoSideScroll();
}

/**
 * A finger's tap: pointer events with `pointerType: "touch"`, then the click a
 * browser sends after them. `userEvent.click` is a mouse, and a mouse press
 * takes the page out of touch.
 */
async function tap(target: HTMLElement): Promise<void> {
  const at = { bubbles: true, pointerType: "touch", isPrimary: true };
  target.dispatchEvent(new PointerEvent("pointerdown", at));
  target.dispatchEvent(new PointerEvent("pointerup", at));
  target.click();
  await new Promise((resolve) => requestAnimationFrame(resolve));
}

const on = (viewport: string) => ({ viewport: { value: viewport }, input: "touch" });

/* --------------------------------------------------------------- upright */

/** Your turn, a few lands down, on the iPhone 15. The everyday case. */
export const IPhone15Board: Story = {
  args: board(scenarios.earlyBoard()),
  globals: on("iphone15"),
  play: async ({ canvasElement }) => {
    await holds(canvasElement, "iphone15");
    // The sheet is the panel, and the slab that ends the decision is in it.
    const sheet = canvasElement.querySelector(".rail--right") as HTMLElement;
    expect(sheet.querySelector('[data-testid="action-panel"]')).not.toBeNull();
    const slab = sheet.querySelector(".commit-dock") as HTMLElement;
    expect(slab.getBoundingClientRect().bottom).toBeLessThanOrEqual(window.innerHeight + 1);
  },
};

export const Pixel7Board: Story = {
  args: board(scenarios.earlyBoard()),
  globals: on("pixel7"),
  play: async ({ canvasElement }) => holds(canvasElement, "pixel7"),
};

export const IPhoneDuoBoard: Story = {
  args: board(scenarios.earlyBoard()),
  globals: on("iphoneduo"),
  play: async ({ canvasElement }) => holds(canvasElement, "iphoneduo"),
};

/**
 * Four seats, full boards: the opponents are one row of orbs, and a tap on one
 * opens that seat's board where the viewer's was.
 */
export const IPhone15Pod: Story = {
  args: board(scenarios.fourPlayerPod()),
  globals: on("iphone15"),
  play: async ({ canvasElement }) => {
    await holds(canvasElement, "iphone15");
    const seats = [...canvasElement.querySelectorAll<HTMLElement>(".play__opponents .seat")];
    expect(seats.length).toBe(3);
    // One row: every orb shares the first one's top.
    const top = seats[0].getBoundingClientRect().top;
    for (const seat of seats)
      expect(Math.abs(seat.getBoundingClientRect().top - top)).toBeLessThan(2);
    await userEvent.click(seats[0]);
    await within(canvasElement).findByTestId("viewing-strip");
  },
};

export const Pixel7DeclareAttackers: Story = {
  args: board(scenarios.combatDeclareAttackers()),
  globals: on("pixel7"),
  play: async ({ canvasElement }) => holds(canvasElement, "pixel7"),
};

export const IPhoneDuoStack: Story = {
  args: board(scenarios.stackThreeDeep()),
  globals: on("iphoneduo"),
  play: async ({ canvasElement }) => holds(canvasElement, "iphoneduo"),
};

/**
 * The drawer. Closing it gives the board the hand's height; the tab says how
 * many cards are in it, and opening it brings the fan back.
 */
export const IPhone15HandDrawer: Story = {
  args: board(scenarios.earlyBoard()),
  globals: on("iphone15"),
  play: async ({ canvasElement }) => {
    await holds(canvasElement, "iphone15");
    const canvas = within(canvasElement);
    const mine = canvasElement.querySelector(".play__mine") as HTMLElement;
    const before = mine.getBoundingClientRect().height;
    await userEvent.click(canvas.getByTestId("hand-drawer"));
    await waitFor(() => expect(canvasElement.querySelector(".hand")).not.toBeVisible());
    expect(canvas.getByTestId("hand-drawer").textContent).toMatch(/Hand \d+/);
    await waitFor(() => expect(mine.getBoundingClientRect().height).toBeGreaterThan(before));
    expectHandheldFloors(canvasElement);
    expectNoSideScroll();
    await userEvent.click(canvas.getByTestId("hand-drawer"));
    await waitFor(() => expect(canvasElement.querySelector(".hand")).toBeVisible());
  },
};

/**
 * The sheet's voice. A tap on a hand card a tap cannot play selects it, and
 * its "why not" is said in the sheet rather than over the hand; a second tap
 * reads it full screen.
 */
export const IPhone15WhyNot: Story = {
  args: board(scenarios.openingHand()),
  globals: on("iphone15"),
  play: async ({ canvasElement }) => {
    await holds(canvasElement, "iphone15");
    const canvas = within(canvasElement);
    // Thragtusk: five mana on turn one.
    const card = canvasElement.querySelector('.hand [data-oid="107"]') as HTMLElement;
    await tap(card);
    expect(document.documentElement.getAttribute("data-input")).toBe("touch");
    const say = canvas.getByTestId("sheet-say");
    await waitFor(() => expect(within(say).getByTestId("unplayable-hint")).toBeVisible());
    await tap(card);
    await canvas.findByTestId("card-hold");
    useUiStore.getState().hover(null);
  },
};

/** A spell waiting for its target says so in the sheet, beside its Cancel. */
export const IPhone15Targeting: Story = {
  args: (() => {
    const scenario = scenarios.earlyBoard();
    // A spell aimed at a player, so the board is waiting on a target.
    const aimed = action({
      id: "t1",
      kind: "cast_spell",
      label: "Cast Counterspell",
      base_label: "Cast Counterspell",
      source_oid: 211,
      targets: [{ kind: "player", id: 1 }],
    });
    return board({ ...scenario, actions: [...scenario.actions, aimed] });
  })(),
  globals: on("iphone15"),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    useUiStore.getState().beginTargeting(211, ["t1"]);
    const say = canvas.getByTestId("sheet-say");
    await waitFor(() => expect(within(say).getByTestId("targeting-hint")).toBeVisible());
    expect(canvasElement.querySelectorAll('[data-testid="targeting-hint"]')).toHaveLength(1);
    await holds(canvasElement, "iphone15");
    useUiStore.getState().endTargeting();
  },
};

/* -------------------------------------------------------------- sideways */

export const IPhone15Landscape: Story = {
  args: board(scenarios.earlyBoard()),
  globals: on("iphone15-landscape"),
  play: async ({ canvasElement }) => holds(canvasElement, "iphone15-landscape"),
};

export const Pixel7Landscape: Story = {
  args: board(scenarios.fourPlayerPod()),
  globals: on("pixel7-landscape"),
  play: async ({ canvasElement }) => holds(canvasElement, "pixel7-landscape"),
};

export const IPhoneDuoLandscape: Story = {
  args: board(scenarios.combatDeclareAttackers()),
  globals: on("iphoneduo-landscape"),
  play: async ({ canvasElement }) => holds(canvasElement, "iphoneduo-landscape"),
};
