/**
 * The hand, fanned on an arc.
 *
 * Every slot here is positioned absolutely against `useCardBase()`, so the fan
 * is arithmetic and the arithmetic is the component. jsdom sees none of it --
 * every `getBoundingClientRect` is zeros, so the pitch between two cards, the
 * lift on hover and whether the fan stays inside its foot are all questions that
 * literally cannot be asked anywhere but here.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import type { CardView, UnplayableReason } from "../../api/types";
import { HAND_FAN_W } from "../../logic/zoomFit";
import { expectHandheldFloors, settled } from "../../testing/asserts";
import * as pool from "../../testing/cards";
import { HandFan } from "./HandFan";

/** A hand of `count` cards, cycling the pool so no two are identical. */
function hand(count: number): CardView[] {
  const makers = [
    pool.forest,
    pool.island,
    pool.llanowarElves,
    pool.cultivate,
    pool.counterspell,
    pool.solRing,
    pool.thragtusk,
    pool.serraAngel,
  ];
  return Array.from({ length: count }, (_, i) =>
    makers[i % makers.length]({ oid: 100 + i, zone: "hand" }),
  );
}

const meta = {
  title: "Game/HandFan",
  component: HandFan,
  parameters: { commanderblitz: { mount: "tableFoot" } },
  args: { onActivate: fn(), onDropOn: fn(), selectedOid: null },
} satisfies Meta<typeof HandFan>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = {
  args: { cards: [], playableOids: new Set() },
};

export const OneCard: Story = {
  args: { cards: hand(1), playableOids: new Set([100]) },
};

export const SevenCards: Story = {
  args: { cards: hand(7), playableOids: new Set([100, 101]) },

  /*
   * The fan is an arc, so the slots must be evenly pitched and rise towards the
   * middle. A fan that collapsed to a stack, or one whose solver returned the
   * floor, still renders seven cards -- the pitch is the only thing that tells
   * them apart.
   */
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Forest");
    expect(canvasElement.querySelectorAll(".hand .card")).toHaveLength(7);

    /*
     * `offsetLeft`, not `getBoundingClientRect`. The slot is what `left: index *
     * step` positions, but the slot is *also* what carries the arc's rotation --
     * and a rotated box is wider than the thing inside it, so its client rect
     * left edge is not evenly pitched even when the layout underneath is
     * perfectly regular. `offsetLeft` is the position before transforms, which
     * is the arithmetic this is about. The rotation is checked separately, by
     * `TheArc`.
     */
    const slots = [...canvasElement.querySelectorAll<HTMLElement>(".hand__slot")];
    const pitches = slots.slice(1).map((slot, i) => slot.offsetLeft - slots[i].offsetLeft);
    expect(
      Math.min(...pitches),
      "slots run backwards or sit on top of each other",
    ).toBeGreaterThan(0);
    expect(
      Math.max(...pitches) - Math.min(...pitches),
      "the fan is not evenly pitched",
    ).toBeLessThan(1);
  },
};

/**
 * The arc: the outer cards sit lower than the middle ones, at any hand size.
 *
 * Measured on `.hand__lift`, because the slot deliberately does not move -- it is
 * the hit box, and holding it still is what stopped the hover jittering.
 *
 * Seven and fifteen, because the bug only showed at fifteen. The droop used to be
 * `min(12, distance ** 2 * 1.4)`, which reaches its ceiling at |distance| >= 2.93
 * -- so a seven-card hand curved and a fifteen-card hand was flat across its
 * outer two-thirds while the rotation kept increasing, which reads as the end
 * cards riding up.
 */
function droops(root: HTMLElement): number[] {
  /*
   * Read from the transform matrix, not from `getBoundingClientRect`.
   *
   * The droop is a translate and the arc also *rotates* each card, and a rotated
   * box's top edge sits higher than the card's -- its corners stick up. So the
   * client rect mixes the two and the middle card, which has no rotation at all,
   * measures lower than its tilted neighbours. `f` is the matrix's translateY,
   * which is exactly the quantity `droop()` produces.
   */
  return [...root.querySelectorAll(".hand__lift")].map(
    (s) => new DOMMatrix(getComputedStyle(s).transform).f,
  );
}

/** Droop must increase from the middle outwards, with no flat run at the edge. */
function expectParabola(root: HTMLElement, count: number) {
  const ys = droops(root);
  expect(ys).toHaveLength(count);
  const left = ys.slice(0, Math.floor((count - 1) / 2) + 1);
  for (let i = 1; i < left.length; i += 1) {
    expect(
      left[i],
      `card ${i} droops as much as card ${i - 1}: the arc is flat here`,
    ).toBeLessThan(left[i - 1]);
  }
  // And the outermost card is the full droop, so the curve uses its whole range
  // rather than saturating early.
  expect(Math.round(ys[0]), "the outer card is not at full droop").toBe(12);
}

export const TheArc: Story = {
  args: { cards: hand(7), playableOids: new Set() },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Forest");
    expectParabola(canvasElement, 7);
  },
};

/** The same curve, at more than twice the cards. */
export const TheArcAtFifteen: Story = {
  args: { cards: hand(15), playableOids: new Set() },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findAllByText("Forest");
    expectParabola(canvasElement, 15);
  },
};

/**
 * Hovering lifts the card and does not move the hit box.
 *
 * That separation *is* the fix for the jitter. When one element carried both the
 * transform and the pointer handlers, raising the card 46px took its box out from
 * under the cursor: `mouseleave` fired, the card settled back under the cursor,
 * `mouseenter` fired, and it oscillated for as long as you rested near an edge.
 *
 * Asserted as the invariant rather than by trying to reproduce the flicker: the
 * slot's rectangle must be identical before and after, and the card inside it
 * must have moved. A test that chased the oscillation itself would be chasing a
 * race.
 */
export const HoverDoesNotMoveTheHitBox: Story = {
  args: { cards: hand(5), playableOids: new Set([100]) },
  parameters: { commanderblitz: { mount: "tableFoot", motion: "real" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Forest");
    const slot = canvasElement.querySelectorAll<HTMLElement>(".hand__slot")[2];
    const lift = slot.querySelector(".hand__lift") as HTMLElement;

    const boxBefore = slot.getBoundingClientRect();
    const cardBefore = lift.getBoundingClientRect().top;

    await userEvent.hover(slot);
    await settled(lift);

    const boxAfter = slot.getBoundingClientRect();
    expect(
      Math.round(boxAfter.top),
      "the hit box moved with the card, which is what made the hover jitter",
    ).toBe(Math.round(boxBefore.top));
    expect(lift.getBoundingClientRect().top, "the card did not lift at all").toBeLessThan(
      cardBefore,
    );
  },
};

/**
 * Fifteen cards, which is well past what the fan was designed around.
 *
 * The cards must tighten rather than the fan growing wider than its foot.
 */
export const FifteenCards: Story = {
  args: { cards: hand(15), playableOids: new Set() },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    // Fifteen cards from an eight-card pool, so several names repeat.
    await canvas.findAllByText("Forest");
    expect(canvasElement.querySelectorAll(".hand .card")).toHaveLength(15);

    /*
     * The budget is the point. `handStep` divides `HAND_FAN_W` between the
     * cards, so a fifteen-card hand tightens its pitch rather than growing a
     * rail wider than the foot it sits in -- and each card must still leave a
     * fifth of its neighbour showing, or the fan reads as one striped object.
     */
    const rail = canvasElement.querySelector<HTMLElement>(".hand__rail") as HTMLElement;
    expect(rail.offsetWidth).toBeLessThanOrEqual(HAND_FAN_W);

    // Pre-transform again, for the reason `SevenCards` explains.
    const slots = [...canvasElement.querySelectorAll<HTMLElement>(".hand__slot")];
    const step = slots[1].offsetLeft - slots[0].offsetLeft;
    expect(
      step / slots[0].offsetWidth,
      "cards overlap past the point the fan stays readable",
    ).toBeGreaterThan(0.19);
  },
};

/**
 * Every reason a card can be unplayable.
 *
 * A dimmed card with no explanation is the complaint this map answers, so all
 * five values are posed at once.
 */
export const WithUnplayableReasons: Story = {
  args: {
    cards: hand(5),
    playableOids: new Set(),
    reasons: {
      100: "priority",
      101: "timing",
      102: "land_drop",
      103: "mana",
      104: "targets",
    } as Record<string, UnplayableReason>,
  },
};

export const SelectedCard: Story = {
  args: { cards: hand(5), playableOids: new Set([100, 101]), selectedOid: 102 },
};

/** Input gated: narration is playing or a request is in flight. */
export const Disabled: Story = {
  args: { cards: hand(5), playableOids: new Set([100]), disabled: true },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const card = await canvas.findByText("Forest");
    await userEvent.click(card);
    expect(args.onActivate).not.toHaveBeenCalled();
  },
};

export const ClickingACard: Story = {
  args: { cards: hand(3), playableOids: new Set([100]) },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByText("Forest"));
    expect(args.onActivate).toHaveBeenCalled();
  },
};

/** Seven cards in the compact foot: the fan still clears the card floor. */
export const SevenCardsHandheld: Story = {
  args: { cards: hand(7), playableOids: new Set([100, 101]) },
  globals: { viewport: { value: "deck" } },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const fan = canvasElement.querySelector<HTMLElement>(".hand") ?? canvasElement;
    await settled(fan);
    expectHandheldFloors(canvasElement);
  },
};
