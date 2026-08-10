/**
 * One player's side of the table.
 *
 * The band order is the thing worth posing: each player's lands sit nearest
 * *them*, so an opponent's mat is `mirrored` and the viewer's is not -- their
 * lands go against their own edge of the screen, and the two creature bands meet
 * across the middle of the table. Both orders render perfectly well, which is
 * why a flipped `LANES` or a dropped `mirrored` prop is only ever visible as a
 * comparison of two numbers.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, within } from "storybook/test";
import { CARD_SCALE, opponentCardScale } from "../../logic/cardSize";
import * as scenarios from "../../testing/scenarios";
import { PlayerMat } from "./PlayerMat";

const early = scenarios.earlyBoard().state;
const crowded = scenarios.crowdedBoard().state;
const attached = scenarios.withAttachments().state;

function mat(state = early, pid = 0, overrides = {}) {
  return {
    state,
    player: state.players[pid],
    names: state.players.map((p) => p.name),
    cardScale: CARD_SCALE.own,
    actionableOids: new Set<number>(),
    onActivate: fn(),
    onDropOn: fn(),
    onSelectPlayer: fn(),
    onCastCommander: fn(),
    ...overrides,
  };
}

const meta = {
  title: "Game/PlayerMat",
  component: PlayerMat,
  parameters: { automtg: { mount: "playMine" } },
} satisfies Meta<typeof PlayerMat>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * The viewer's mat: lands at the bottom, nearest their hand.
 *
 * Note it is *not* mirrored -- `mirrored` is what an opponent's mat gets, so
 * their lands sit against their own edge of the screen and the two creature
 * bands meet across the middle of the table. Getting that backwards produces a
 * board that looks entirely deliberate, which is why the assertion is a
 * comparison of two numbers rather than anything about content.
 */
export const Viewer: Story = {
  args: mat(early, 0),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findAllByText("Forest");
    // The lane identifies itself by its drop-zone key, `lane:{pid}:{name}`.
    const lands = canvasElement.querySelector('[data-dropzone="lane:0:Lands"]') as HTMLElement;
    const creatures = canvasElement.querySelector(
      '[data-dropzone="lane:0:Creatures"]',
    ) as HTMLElement;
    expect(
      lands.getBoundingClientRect().top,
      "the viewer's lands should be the band nearest them",
    ).toBeGreaterThan(creatures.getBoundingClientRect().top);
  },
};

/**
 * An opponent's mat: the same bands, the other way up.
 *
 * Their lands are nearest *them*, which from the viewer's side of the table
 * means the top band. This and `Viewer` are the pair -- neither is meaningful
 * alone, because each looks entirely deliberate on its own.
 */
export const Opponent: Story = {
  parameters: { automtg: { mount: "playOpponents" } },
  args: (() => {
    // Not `earlyBoard`: its opponent controls nothing, and a compact mat hides
    // empty lanes -- so there would be no bands to compare. This one has a
    // creature and a land.
    const state = scenarios.combatDeclareAttackers().state;
    return mat(state, 1, { compact: true, mirrored: true, cardScale: opponentCardScale(2) });
  })(),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("player-1");
    const lands = canvasElement.querySelector('[data-dropzone="lane:1:Lands"]') as HTMLElement;
    const creatures = canvasElement.querySelector(
      '[data-dropzone="lane:1:Creatures"]',
    ) as HTMLElement;
    expect(
      lands.getBoundingClientRect().top,
      "an opponent's lands should be the band nearest them",
    ).toBeLessThan(creatures.getBoundingClientRect().top);
  },
};

/**
 * An opponent controlling nothing.
 *
 * A compact mat drops its empty lanes rather than reserving them -- three
 * opponents at full width wrapped their creatures onto a second row and pushed
 * the viewer's whole board down. The viewer's mat makes the opposite trade, and
 * `Viewer` is where that shows.
 */
export const OpponentWithEmptyBoard: Story = {
  parameters: { automtg: { mount: "playOpponents" } },
  args: mat(early, 1, { compact: true, mirrored: true, cardScale: opponentCardScale(1) }),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("player-1");
    expect(canvasElement.querySelectorAll("[data-dropzone]")).toHaveLength(0);
  },
};

export const OpponentInAFourPlayerPod: Story = {
  parameters: { automtg: { mount: "playOpponents" } },
  args: (() => {
    const state = scenarios.fourPlayerPod().state;
    return mat(state, 2, { compact: true, mirrored: true, cardScale: opponentCardScale(3) });
  })(),
};

/** Twelve basics, collapsed into counted piles rather than twelve cards. */
export const CrowdedLands: Story = {
  args: mat(crowded, 0),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findAllByText("Forest");
    expect(canvasElement.querySelectorAll("[data-stack-count]").length).toBeGreaterThan(0);
  },
};

/**
 * A creature wearing an Aura and an Equipment.
 *
 * Neither shipped precon contains one, so no game and no e2e run can currently
 * reach this path -- `tests/playerMat.test.tsx` and this story are its only
 * coverage until the card catalogue grows.
 */
export const WithAttachments: Story = {
  args: mat(attached, 0),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Serra Angel");
    await canvas.findByText("Rancor");
  },
};

/** A lane lit as a legal destination for whatever is being dragged. */
export const ActiveDropLane: Story = {
  args: mat(early, 0, {
    draggable: true,
    activeLanes: new Set(["Lands"]),
  }),
};

export const TargetableCards: Story = {
  args: mat(early, 0, {
    isTargetable: () => true,
    actionableOids: new Set([205]),
  }),
};

export const StagedAttackers: Story = {
  args: (() => {
    const state = scenarios.combatDeclareAttackers().state;
    return mat(state, 0, { isStaged: (c: { oid: number }) => c.oid === 302 });
  })(),
};

/** This player can be pointed at right now. */
export const PlayerTargetable: Story = {
  parameters: { automtg: { mount: "playOpponents" } },
  args: mat(early, 1, { compact: true, mirrored: true, playerTargetable: true }),
};

/** Input gated while narration plays. */
export const Locked: Story = {
  args: mat(early, 0, { locked: true }),
};
