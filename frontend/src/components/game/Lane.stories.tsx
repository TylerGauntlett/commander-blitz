/**
 * One band of the battlefield.
 *
 * The lane is also the drop target, and it is where identical permanents
 * collapse into counted piles. Both of those are geometry: a pile is a pile
 * because its members are offset by a few pixels, and a drop target is one
 * because it has an area.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, within } from "storybook/test";
import { CARD_SCALE } from "../../logic/cardSize";
import { expectFontFloor, expectHitFloor } from "../../testing/asserts";
import * as pool from "../../testing/cards";
import { Lane } from "./Lane";

const meta = {
  title: "Game/Lane",
  component: Lane,
  parameters: { automtg: { mount: "bandFront" } },
  args: {
    pid: 0,
    cardScale: CARD_SCALE.own,
    actionableOids: new Set<number>(),
    onActivate: fn(),
    onDropOn: fn(),
  },
} satisfies Meta<typeof Lane>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Creatures: Story = {
  args: {
    lane: "Creatures",
    cards: [
      pool.grizzlyBears({ oid: 1 }),
      pool.serraAngel({ oid: 2 }),
      pool.thragtusk({ oid: 3, tapped: true }),
      pool.krakenToken({ oid: 4, summoning_sick: true }),
    ],
  },
};

export const Lands: Story = {
  parameters: { automtg: { mount: "bandBack" } },
  args: {
    lane: "Lands",
    cards: [
      pool.forest({ oid: 10 }),
      pool.island({ oid: 11 }),
      pool.swamp({ oid: 12, tapped: true }),
      pool.breedingPool({ oid: 13 }),
    ],
  },
};

export const ArtifactsAndEnchantments: Story = {
  args: {
    lane: "Artifacts & Enchantments",
    cards: [pool.solRing({ oid: 20 }), pool.rhysticStudy({ oid: 21 })],
  },
};

/** Empty lanes still hold their band, so the board does not jump as it fills. */
export const Empty: Story = {
  args: { lane: "Creatures", cards: [] },
};

/**
 * Twelve basics, which is two cards on screen.
 *
 * Stacking is cosmetic and it must be *visible* as stacking: a pile carries its
 * count, and its members really are offset rather than superimposed.
 */
export const TwelveBasicsStacked: Story = {
  parameters: { automtg: { mount: "bandBack" } },
  args: {
    lane: "Lands",
    cards: [
      ...Array.from({ length: 7 }, (_, i) => pool.forest({ oid: 30 + i })),
      ...Array.from({ length: 5 }, (_, i) => pool.island({ oid: 40 + i })),
    ],
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findAllByText("Forest");
    const piles = [...canvasElement.querySelectorAll("[data-stack-count]")];
    expect(piles.map((p) => p.getAttribute("data-stack-count"))).toEqual(["7", "5"]);
  },
};

/**
 * A legal action names three of seven Forests.
 *
 * Stacking must never bury a choice, so the named ones split out of the pile
 * and stay individually clickable.
 */
export const ActionableSplitOut: Story = {
  parameters: { automtg: { mount: "bandBack" } },
  args: {
    lane: "Lands",
    cards: Array.from({ length: 7 }, (_, i) => pool.forest({ oid: 30 + i })),
    actionableOids: new Set([30, 31, 32]),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findAllByText("Forest");
    const counts = [...canvasElement.querySelectorAll("[data-stack-count]")].map((p) =>
      p.getAttribute("data-stack-count"),
    );
    // Three reachable, four collapsed behind one count.
    expect(counts).toContain("4");
  },
};

/** Highlighted as a legal destination for whatever is being dragged. */
export const ActiveDropTarget: Story = {
  parameters: { automtg: { mount: "bandBack" } },
  args: {
    lane: "Lands",
    cards: [pool.forest({ oid: 10 })],
    active: true,
    draggable: true,
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Forest");
    const zone = canvasElement.querySelector("[data-dropzone]");
    expect(zone, "the lane is not a drop target").not.toBeNull();
    const box = (zone as HTMLElement).getBoundingClientRect();
    expect(
      box.width * box.height,
      "a drop target with no area cannot be dropped on",
    ).toBeGreaterThan(0);
  },
};

/** Rims: a legal action could point at these. */
export const TargetableCards: Story = {
  args: {
    lane: "Creatures",
    cards: [pool.grizzlyBears({ oid: 1 }), pool.serraAngel({ oid: 2 })],
    isTargetable: (card) => card.oid === 2,
    actionableOids: new Set([2]),
  },
};

/** Staged as an attacker, not yet submitted. */
export const StagedForCombat: Story = {
  args: {
    lane: "Creatures",
    cards: [pool.grizzlyBears({ oid: 1 }), pool.serraAngel({ oid: 2 })],
    isStaged: (card) => card.oid === 1,
  },
};

/** A creature wearing an Aura and an Equipment, drawn tucked behind it. */
export const WithAttachments: Story = {
  args: {
    lane: "Creatures",
    cards: [pool.serraAngel({ oid: 50 })],
    attachments: new Map([
      [
        50,
        [
          pool.rancor({ oid: 51, attached_to: 50 }),
          pool.swordOfFireAndIce({ oid: 52, attached_to: 50 }),
        ],
      ],
    ]),
  },
};

/** The same creatures on a Deck: every card at the floor, every label legible. */
export const CreaturesHandheld: Story = {
  args: Creatures.args,
  globals: { handheld: "on" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Grizzly Bears");
    // Type and targets only. The card width here is the fixture's fixed
    // `cardScale`, not the zoom solver's answer; the 96px card floor is
    // asserted where the solver runs, in `Table.stories.tsx`.
    expectFontFloor(canvasElement);
    expectHitFloor(canvasElement);
  },
};
