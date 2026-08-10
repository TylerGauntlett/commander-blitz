/**
 * A card as an interactive object, rather than as a face.
 *
 * `CardFace` draws the printed card; `Card` wraps it in the two motion layers
 * that make it a thing on a table -- the outer one owns position, drag and the
 * `layoutId` that carries it between zones, the inner one owns the tap rotation.
 * The rims are the whole vocabulary of "what can I do with this", so they are
 * posed together where they can be compared.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, waitFor, within } from "storybook/test";
import * as pool from "../../testing/cards";
import { Card, StaticCard } from "./Card";

const meta = {
  title: "Game/Card",
  component: Card,
  parameters: { automtg: { mount: "laneCards" } },
  args: { card: pool.grizzlyBears(), onActivate: fn(), onDropOn: fn() },
} satisfies Meta<typeof Card>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/**
 * Tapped, which is a quarter turn on the inner layer.
 *
 * The rotation lives on `.card__pivot` rather than on the card itself, because
 * the outer layer owns position and drag and `layoutId` -- a single element
 * doing both would have the tap fighting the move between zones.
 */
export const Tapped: Story = {
  args: { card: pool.grizzlyBears({ tapped: true }) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Grizzly Bears");
    const pivot = canvasElement.querySelector(".card__pivot") as HTMLElement;
    /*
     * Waited for, not read straight away.
     *
     * `reducedMotion` cuts the tween, not the value -- the card really does end
     * up at `rotate(90deg)` -- but Motion still writes the transform on its
     * first frame rather than during render, so a synchronous read here sees
     * `none` and the story fails against a card that is visibly on its side.
     * The same reason play functions use `findBy*` over `getBy*`.
     */
    await waitFor(() =>
      expect(getComputedStyle(pivot).transform, "a tapped card should be rotated").not.toBe(
        "none",
      ),
    );
    // Rotated a quarter turn, so its box is wider than it is tall.
    const box = (canvasElement.querySelector(".card") as HTMLElement).getBoundingClientRect();
    expect(box.width).toBeGreaterThan(box.height);
  },
};

/** Untapped, for the comparison the story above needs to mean anything. */
export const Untapped: Story = {
  args: { card: pool.grizzlyBears({ tapped: false }) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Grizzly Bears");
    const pivot = canvasElement.querySelector(".card__pivot") as HTMLElement;
    const transform = getComputedStyle(pivot).transform;
    // Either no transform at all, or the identity matrix.
    expect(["none", "matrix(1, 0, 0, 1, 0, 0)"]).toContain(transform);
  },
};

/**
 * Every rim, side by side.
 *
 * The whole vocabulary of "what is true about this card", and it only works as a
 * set -- each rim is only legible against the others. Green is "a legal action
 * would play this", blue "something could target it", amber "staged for combat,
 * not sent yet", white "selected", dimmed "nothing to do with it right now".
 *
 * The last two come from the *card*, not from a prop: `Card` reads
 * `card.attacking` and `card.blocking` and emits `.card--attacking` /
 * `.card--blocking`, which is why they were missing here -- every other rim is a
 * prop, so a set built by listing props left out the two that are not.
 */
export const TheRims: Story = {
  render: () => (
    <div style={{ display: "flex", gap: 12 }}>
      <Card card={pool.grizzlyBears({ oid: 1 })} playable />
      <Card card={pool.serraAngel({ oid: 2 })} targetable />
      <Card card={pool.thragtusk({ oid: 3 })} staged />
      <Card card={pool.wallOfRoots({ oid: 4 })} selected />
      <Card card={pool.llanowarElves({ oid: 5 })} dimmed />
      <Card card={pool.grizzlyBears({ oid: 6, attacking: true })} />
      <Card card={pool.serraAngel({ oid: 7, blocking: true })} />
    </div>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findAllByText("Grizzly Bears");
    expect(canvasElement.querySelectorAll(".card--attacking")).toHaveLength(1);
    expect(canvasElement.querySelectorAll(".card--blocking")).toHaveLength(1);
  },
};

/** In combat, from the engine's own view of the board. */
export const Attacking: Story = {
  args: { card: pool.thragtusk({ attacking: true }) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Thragtusk");
    expect(canvasElement.querySelector(".card--attacking")).not.toBeNull();
  },
};

export const Blocking: Story = {
  args: { card: pool.wallOfRoots({ blocking: true }) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Wall of Roots");
    expect(canvasElement.querySelector(".card--blocking")).not.toBeNull();
  },
};

export const Playable: Story = { args: { playable: true } };
export const Targetable: Story = { args: { targetable: true } };
export const Staged: Story = { args: { staged: true } };
export const Selected: Story = { args: { selected: true } };
export const Dimmed: Story = { args: { dimmed: true } };

/** An activated ability, announced in a popover while the card is hovered. */
export const WithAbility: Story = {
  args: {
    card: pool.llanowarElves(),
    hasAbility: true,
    abilityLabel: "{T}: Add {G}",
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const card = await canvas.findByText("Llanowar Elves");
    await userEvent.hover(card);
    await canvas.findByText(/Add/);
  },
};

export const Clicking: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByText("Grizzly Bears"));
    expect(args.onActivate).toHaveBeenCalled();
  },
};

/**
 * The static variant, which is the same face with none of the machinery.
 *
 * Used wherever a card is being *shown* rather than played -- the prompt
 * dialog's options, the zone viewer, the stack.
 */
export const Static: Story = {
  render: () => (
    <div style={{ display: "flex", gap: 12 }}>
      <StaticCard card={pool.aesi({ zone: "battlefield" })} variant="detail" />
      <StaticCard card={pool.counterspell()} variant="detail" />
    </div>
  ),
};
