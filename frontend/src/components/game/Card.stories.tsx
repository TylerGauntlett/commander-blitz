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
import { useState } from "react";
import { expect, fn, userEvent, waitFor, within } from "storybook/test";
import { reset as forgetRects, recall } from "../../logic/cardRects";
import * as pool from "../../testing/cards";
import { Card, StaticCard } from "./Card";

const meta = {
  title: "Game/Card",
  component: Card,
  parameters: { commanderblitz: { mount: "laneCards" } },
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
    const card = canvasElement.querySelector(".card") as HTMLElement;
    const box = card.getBoundingClientRect();
    expect(box.width).toBeGreaterThan(box.height);

    /*
     * And the box is *on* the card. The rims are `.card__actor::after`, and
     * `.card__actor` is 100% of this outer box, so a box that has the right
     * shape in the wrong place draws a border beside the card rather than round
     * it.
     *
     * Here the card is a flex item -- `laneCards` ends in `.lane__cards`, which
     * is `display: flex` -- and that is a formatting context root, so this was
     * green even while the board was visibly broken. The case that actually
     * broke is `CardStack.AllTapped`; this one holds the other context.
     */
    const face = pivot.getBoundingClientRect();
    for (const edge of ["top", "bottom", "left", "right"] as const) {
      expect(
        Math.abs(box[edge] - face[edge]),
        `the rim's ${edge} edge is not on the tapped card's ${edge} edge`,
      ).toBeLessThan(1);
    }
  },
};

/**
 * THE RIM IS INSIDE THE TRANSFORM, WHICH IS THE FIX FOR "THE GLOW DOES NOT GO
 * ROUND THE CARD".
 *
 * `fx/actuators.ts`'s `lean` eases in and *stays*: a staged attacker holds a
 * translate, a tilt of up to 6deg and a 1.03 scale on `.card__actor` for as long
 * as it is declared. While the rim was a pseudo-element of `.card` -- the
 * PARENT of the node carrying that transform -- the card stepped out from under
 * its own halo, and the pin stayed behind with it. Both are painted on
 * `.card__actor` now.
 *
 * The lean itself is driven from `Table`, so this poses the geometry rather than
 * the actuator: it writes the transform this story's subject would be holding
 * and asserts what has to be true of it. Tapped as well as staged, because the
 * two compose -- the outer box swaps to landscape, the pivot turns inside it,
 * and the rim has to end up round the result either way.
 */
export const StagedAndTapped: Story = {
  args: { card: pool.grizzlyBears({ tapped: true }), staged: true },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Grizzly Bears");
    const card = canvasElement.querySelector(".card") as HTMLElement;
    const actor = canvasElement.querySelector(".card__actor") as HTMLElement;

    // 1. The rim is on the actor, and is not on the outer box any more. A
    //    pseudo-element has no rect to measure, so this is the only direct
    //    reading of *which element it is painted on* available.
    expect(
      getComputedStyle(actor, "::after").content,
      "the rim should be on .card__actor",
    ).toBe('""');
    expect(
      getComputedStyle(card, "::after").content,
      "the rim should no longer be on .card",
    ).toBe("none");

    // 2. And it is lit: `.card--staged` is a class on `.card`, so the state and
    //    the paint are on different elements and the selector has to bridge them.
    await waitFor(() =>
      expect(
        getComputedStyle(actor, "::after").boxShadow,
        "a staged card should carry the amber rim",
      ).not.toBe("none"),
    );

    // 3. The pin travels with the card rather than staying on the outer box.
    const pin = canvasElement.querySelector(".card__pin") as HTMLElement;
    expect(pin, "a staged card has a pin").toBeTruthy();
    expect(actor.contains(pin), "the pin belongs inside .card__actor").toBe(true);

    /*
     * 4. The actual defect: a transform written where `lean` writes it moves the
     *    rim with the card. `.card__actor`'s rect *is* the rim's rect inset by
     *    3px, so its moving is the rim's moving -- and `.card` holding still is
     *    what the arrows and the death ghost depend on, since they measure
     *    `[data-oid]` on the outer box.
     */
    const before = { card: card.getBoundingClientRect(), actor: actor.getBoundingClientRect() };
    actor.style.transform = "translate(14px, -9px) rotate(6deg) scale(1.03)";
    await waitFor(() =>
      expect(actor.getBoundingClientRect().top).not.toBeCloseTo(before.actor.top, 1),
    );
    const after = { card: card.getBoundingClientRect(), actor: actor.getBoundingClientRect() };
    expect(after.card.top, "the layout box must not move with the lean").toBeCloseTo(
      before.card.top,
      1,
    );
    expect(after.card.left).toBeCloseTo(before.card.left, 1);
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

/**
 * A card posts its last position on the way out.
 *
 * The contract behind the whole exit animation: React runs a layout effect's
 * cleanup *before* it detaches the node, so `Card` can still measure itself
 * there. Without it a destroyed permanent has no recorded position and the
 * ghost has nowhere to fly from -- which is the state the board was in.
 *
 * This is the only tier that can prove it. jsdom reports every box as 0x0 and
 * `remember` rejects zero-sized rects on purpose, so a unit test would assert
 * against a registry that correctly refused to store anything.
 */
export const RemembersItsRectOnUnmount: Story = {
  render: () => {
    const [mounted, setMounted] = useState(true);
    return (
      <div>
        <button type="button" data-testid="drop-it" onClick={() => setMounted(false)}>
          Destroy
        </button>
        {mounted && <Card card={pool.grizzlyBears({ oid: 4242 })} />}
      </div>
    );
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    forgetRects();
    await canvas.findByText("Grizzly Bears");
    expect(recall(4242), "nothing is recorded while the card is still up").toBeNull();

    await userEvent.click(canvas.getByTestId("drop-it"));

    await waitFor(() => {
      const box = recall(4242);
      expect(box, "a card should post its box as it unmounts").not.toBeNull();
      // A real measurement, not the zero rect the registry would have dropped.
      expect(box?.width).toBeGreaterThan(0);
      expect(box?.height).toBeGreaterThan(0);
    });
  },
};
