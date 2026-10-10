/**
 * The lit hall the three menu screens stand in.
 *
 * `Room` renders nothing selectable and has no state of its own, so what these
 * stories are for is the two things it OWNS -- the stage scale and the room's
 * colour -- plus the one structural rule nothing else can state: a room nested
 * inside a room is an overlay.
 *
 * All three are cheap to get wrong invisibly. A `--du` that never resolves
 * leaves every size in `pod.css` and `shelf.css` at its fallback, which looks
 * like a slightly-off design rather than like a broken effect; a hue that never
 * reaches the element leaves three screens the same colour; and a nested room
 * that stays in flow lands under its host's furniture with whatever height the
 * flow gave it -- which for the catalogue over the pod was 21px, and read as
 * "the deck browser does not open".
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";
import { POD_HUE, Room, SHELF_HUE, soft } from "./Room";

const meta = {
  title: "Lobby/Room",
  component: Room,
  parameters: { commanderblitz: { mount: "screen" } },
  args: { hue: POD_HUE, children: null },
} satisfies Meta<typeof Room>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The hall, empty. Everything on screen is the room itself. */
export const Empty: Story = {
  args: { testId: "room" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const room = await canvas.findByTestId("room");
    // The drawn hall, the floor sigil, the pool of light and the motes.
    expect(room.querySelector(".room__ground")).not.toBeNull();
    expect(room.querySelector(".room__floor")).not.toBeNull();
    expect(room.querySelector(".room__wash")).not.toBeNull();
    expect(room.querySelectorAll(".mote").length).toBe(16);
  },
};

/**
 * `--du` is exactly 1 at 1280x800, which is a Steam Deck's panel.
 *
 * Not a nicety: every size in `pod.css` and `shelf.css` is `calc(N * var(--du))`
 * with N in the mockup's own pixels, so a Deck gets the composition the design
 * round measured, to the pixel. `data-du` publishes what the screen actually
 * resolved to, so a test can read it rather than recompute `stageScale` and
 * assert against its own arithmetic.
 */
export const StageScale: Story = {
  args: { testId: "room" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const room = await canvas.findByTestId("room");
    const du = Number(room.dataset.du);
    expect(Number.isFinite(du)).toBe(true);
    // The storybook mount is not a Deck, so the assertion is the range rather
    // than the number: below 0.72 the type stops fitting and above 1.45 the
    // furniture is wider than the pool of light it stands in.
    expect(du).toBeGreaterThanOrEqual(0.72);
    expect(du).toBeLessThanOrEqual(1.45);
  },
};

/**
 * The hue reaches the element, so it reaches the floor sigil and the motes.
 *
 * Written as custom properties rather than as classes because the sigil is an
 * SVG `<use>`: `stroke` inherits, inheritance crosses into a shadow tree, and a
 * CSS property can transition where a presentation attribute cannot. One
 * declaration retints every ring, spoke and square in the floor, and does it
 * over `--t-room` rather than cutting.
 */
export const PodLight: Story = {
  args: { hue: POD_HUE, testId: "room" },
  play: async ({ canvasElement }) => {
    const room = await within(canvasElement).findByTestId("room");
    expect(room.style.getPropertyValue("--lit")).toBe(POD_HUE[0]);
    expect(room.style.getPropertyValue("--lit-soft")).toBe(soft(POD_HUE[0], 0.36));
  },
};

/** The catalogue's own light: cold green, the colour the door's Decks card lights. */
export const ShelfLight: Story = {
  args: { hue: SHELF_HUE, testId: "room" },
  play: async ({ canvasElement }) => {
    const room = await within(canvasElement).findByTestId("room");
    expect(room.style.getPropertyValue("--lit")).toBe(SHELF_HUE[0]);
    expect(room.style.getPropertyValue("--lit")).not.toBe(POD_HUE[0]);
  },
};

/**
 * A ROOM INSIDE A ROOM IS AN OVERLAY, and it has to fill its host exactly.
 *
 * The catalogue is a full-bleed hall in its own right and opens over the pod,
 * which is another one. Every one of the pod's own children is absolutely
 * positioned, so an in-flow catalogue was laid out against an empty box -- 21px
 * tall, under the furniture. The rule is a descendant selector rather than a
 * modifier, because "this is on top" is a fact about where the screen was
 * rendered and `DecksRoute` mounts the same component as a route of its own.
 */
export const NestedRoomIsAnOverlay: Story = {
  args: {
    hue: POD_HUE,
    testId: "room",
    children: (
      <Room hue={SHELF_HUE} className="shelf" testId="inner">
        <span />
      </Room>
    ),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const outer = (await canvas.findByTestId("room")).getBoundingClientRect();
    const inner = (await canvas.findByTestId("inner")).getBoundingClientRect();
    expect(getComputedStyle(await canvas.findByTestId("inner")).position).toBe("absolute");
    expect(Math.round(inner.width)).toBe(Math.round(outer.width));
    expect(Math.round(inner.height)).toBe(Math.round(outer.height));
    expect(Math.round(inner.top)).toBe(Math.round(outer.top));
  },
};
