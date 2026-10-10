/**
 * A card leaving the battlefield, on its own.
 *
 * `FxLayer` resolves where a ghost starts, where it ends and how long it lives;
 * this component only flies. Posing it directly is what makes each destination
 * a thing you can look at side by side rather than a moment you have to catch
 * in a running game.
 *
 * These run with real motion (`commanderblitz.motion: "real"`), because with
 * `reducedMotion` the transform under test is exactly what is removed. The
 * assertions are therefore about what is *drawn* -- the caption, the card, the
 * destination class -- and the geometry is left to `FxLayer.stories.tsx`, which
 * has a real board to measure against.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";
import * as pool from "../../testing/cards";
import { CardGhost } from "./CardGhost";

const meta = {
  title: "Game/CardGhost",
  component: CardGhost,
  parameters: { commanderblitz: { mount: "tableBody", motion: "real" } },
  args: {
    oid: 4,
    card: pool.grizzlyBears(),
    name: "Grizzly Bears",
    caption: "Destroyed by Swords to Plowshares",
    to: "graveyard",
    // A long flight held on screen, so the pose is legible in the browser.
    from: { x: 320, y: 260 },
    toPoint: { x: 900, y: 620 },
    width: 96,
    duration: 3.2,
    delay: 0,
  },
} satisfies Meta<typeof CardGhost>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Destroyed: the common case, and the one the whole feature is named for. */
export const ToGraveyard: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Destroyed by Swords to Plowshares");
    const ghost = await canvas.findByTestId("card-ghost");
    expect(ghost.className).toContain("fx-ghost--graveyard");
  },
};

/**
 * Exiled, which is not death.
 *
 * Whether a creature can be recurred is the question a player is actually
 * asking as it leaves, so the two destinations have to be distinguishable at a
 * glance rather than by reading the caption. This one bleaches and glows where
 * the graveyard darkens.
 */
export const ToExile: Story = {
  args: { to: "exile", caption: "Exiled by Leyline of the Void" },
  play: async ({ canvasElement }) => {
    const ghost = await within(canvasElement).findByTestId("card-ghost");
    expect(ghost.className).toContain("fx-ghost--exile");
  },
};

/** Bounced. Nothing died, so nothing mourns: the card keeps its colour. */
export const ToHand: Story = {
  args: { to: "hand", caption: "Returned to hand" },
};

/**
 * A destroyed commander, which lands in the command zone.
 *
 * Rule 903.9a replaces the destination and leaves the cause alone, so the
 * caption has to carry both halves -- "Destroyed" on its own would be a
 * commander that looks lost, and "to the command zone" on its own throws away
 * the reason it left.
 */
export const DestroyedCommander: Story = {
  args: {
    to: "command",
    card: pool.aesi(),
    caption: "Destroyed by Swords to Plowshares — to the command zone",
  },
};

/**
 * A token, which is the fallback and not an edge case.
 *
 * Tokens cease to exist the instant they leave the battlefield, so by the time
 * this beat plays there is no card anywhere in the view to draw. Token deaths
 * are a large fraction of every Commander game, and without the name plate all
 * of them would animate nothing at all.
 */
export const TokenNamePlate: Story = {
  args: { card: null, name: "Beast", caption: "Lethal damage" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Beast");
    // The plate stands in for the card, so there is no card face beside it.
    expect(canvasElement.querySelector(".fx-ghost__card")).toBeNull();
  },
};

/** An unattributed death: the plain form, with no culprit invented. */
export const NoCulprit: Story = {
  args: { caption: "Lethal damage" },
};

/** The longest caption the phrase table can produce, against clipping. */
export const LongCaption: Story = {
  args: { caption: "Paid as a cost for Krark-Clan Ironworks — to the command zone" },
};
