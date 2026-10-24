/**
 * The commander, drawn as a plinth.
 *
 * It is the deck's hero and it is castable in place, so it is not a zone pile
 * with a count -- it is a cropped portrait with a state strip and the tax under
 * it. The tax is keyed by commander *oid*, unlike `commander_damage_taken` next
 * to it, which is keyed by player.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { expectHandheldFloors, settled } from "../../testing/asserts";
import * as pool from "../../testing/cards";
import { gameView, player } from "../../testing/fixtures";
import { CommandZone } from "./CommandZone";

/** A view whose seat 0 holds the given commanders. */
function withCommanders(cards = [pool.aesi({ oid: 900 })], overrides = {}) {
  return gameView({
    players: [
      player({ command: cards, ...overrides }),
      player({ pid: 1, name: "AI 1", hand: null }),
    ],
  });
}

const meta = {
  title: "Game/CommandZone",
  component: CommandZone,
  parameters: { commanderblitz: { mount: "orbBody" } },
  args: {
    pid: 0,
    playableOids: new Set<number>(),
    onActivate: fn(),
    onHover: fn(),
  },
} satisfies Meta<typeof CommandZone>;

export default meta;
type Story = StoryObj<typeof meta>;

export const OneCommander: Story = {
  args: { state: withCommanders() },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Aesi/);
  },
};

/** A partner pair, sharing the plinth. */
export const TwoCommanders: Story = {
  args: {
    state: withCommanders([pool.aesi({ oid: 900 }), pool.edgarMarkov({ oid: 901 })]),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Aesi/);
    await canvas.findByText(/Edgar/);
  },
};

/**
 * Cast twice already, so it costs {4} more.
 *
 * `commander_tax` counts prior casts; `commander_cost` is the extra generic mana
 * owed, already doubled. The plinth shows the mana, not the count.
 */
export const Tax: Story = {
  args: {
    state: withCommanders([pool.aesi({ oid: 900 })], {
      commander_tax: { "900": 2 },
      commander_cost: { "900": 4 },
    }),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Aesi/);
    expect(canvasElement.textContent).toContain("4");
  },
};

/** Affordable right now: the plinth carries its ready state. */
export const Playable: Story = {
  args: { state: withCommanders(), playableOids: new Set([900]) },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByText(/Aesi/));
    expect(args.onActivate).toHaveBeenCalled();
  },
};

/**
 * The plinth is a cropped portrait, so the art is most of it.
 *
 * `.cmdplinth__frame` is `aspect-ratio: 1.16` and the art fills it absolutely,
 * which is why this only reads correctly inside the orb: given the whole canvas
 * the frame becomes a picture a screen wide, and the commander stops looking
 * like a hero and starts looking like a masthead.
 */
export const WithArt: Story = {
  args: { state: withCommanders() },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Aesi/);
    const art = canvasElement.querySelector("[data-art]");
    expect(art?.getAttribute("data-art"), "the plinth drew no art").toBe("ready");
  },
};

/** Loaded, and this commander has no printing: the plate, drawn on purpose. */
export const NoArt: Story = {
  args: { state: withCommanders() },
  parameters: { commanderblitz: { mount: "orbBody", art: "none" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Aesi/);
    expect(canvasElement.querySelector("[data-art]")?.getAttribute("data-art")).toBe("none");
  },
};

/** Already on the battlefield, so the command zone is empty. */
export const Empty: Story = {
  args: { state: withCommanders([]) },
};

/** Input gated. */
export const Disabled: Story = {
  args: { state: withCommanders(), playableOids: new Set([900]), disabled: true },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByText(/Aesi/));
    expect(args.onActivate).not.toHaveBeenCalled();
  },
};

/** The plinth, castable, in the compact orb. */
export const PlayableHandheld: Story = {
  args: Playable.args,
  globals: { viewport: { value: "deck" } },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    await settled(canvasElement);
    expectHandheldFloors(canvasElement);
  },
};
