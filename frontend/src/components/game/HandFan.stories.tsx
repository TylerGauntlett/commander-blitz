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
 * The arc itself: the outer cards droop below the middle ones.
 *
 * `y` is `distance ** 2 * 1.4`, so this is a parabola and the ends are lowest.
 * It survives `reducedMotion` because the value is applied rather than animated
 * -- which is worth knowing, since it means the harness does not flatten the
 * shape it is meant to be checking.
 */
export const TheArc: Story = {
  args: { cards: hand(7), playableOids: new Set() },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Forest");
    const tops = [...canvasElement.querySelectorAll(".hand__slot")].map(
      (s) => s.getBoundingClientRect().top,
    );
    const middle = tops[3];
    expect(middle, "the fan is flat: the middle card should sit highest").toBeLessThan(tops[0]);
    expect(middle).toBeLessThan(tops[6]);
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
