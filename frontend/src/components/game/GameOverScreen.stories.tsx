/**
 * How a game ends.
 *
 * Three outcomes, and they must be distinguishable without reading: `data-result`
 * carries which one, and the class drives the treatment.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { gameView, player } from "../../testing/fixtures";
import * as scenarios from "../../testing/scenarios";
import { GameOverScreen } from "./GameOverScreen";

const meta = {
  title: "Game/GameOverScreen",
  component: GameOverScreen,
  args: { onRematch: fn(), onQuit: fn() },
} satisfies Meta<typeof GameOverScreen>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Victory: Story = {
  args: { state: scenarios.gameOver(0).state },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const over = await canvas.findByTestId("game-over");
    expect(over.dataset.result).toBe("win");
    await canvas.findByText("Victory");
  },
};

export const Defeat: Story = {
  args: { state: scenarios.gameOver(1).state },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const over = await canvas.findByTestId("game-over");
    expect(over.dataset.result).toBe("loss");
    await canvas.findByText("Defeat");
  },
};

/** Nobody won: the turn cap, or everyone losing at once. */
export const Draw: Story = {
  args: {
    state: gameView({
      game_over: true,
      winners: [],
      result: "Draw",
      pending: null,
      players: [
        player({ life: 0, has_lost: true, loss_reason: "life" }),
        player({
          pid: 1,
          name: "AI 1",
          hand: null,
          life: 0,
          has_lost: true,
          loss_reason: "life",
        }),
      ],
    }),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect((await canvas.findByTestId("game-over")).dataset.result).toBe("draw");
  },
};

/** A pod, where the losers each lost for their own reason. */
export const PodWinner: Story = {
  args: {
    state: gameView({
      game_over: true,
      winners: [2],
      result: "AI 2 wins",
      pending: null,
      players: [
        player({ has_lost: true, life: 0, loss_reason: "life" }),
        player({
          pid: 1,
          name: "AI 1",
          hand: null,
          has_lost: true,
          life: 12,
          loss_reason: "commander damage",
        }),
        player({ pid: 2, name: "AI 2", hand: null, life: 31 }),
        player({
          pid: 3,
          name: "AI 3",
          hand: null,
          has_lost: true,
          life: 8,
          loss_reason: "drawing from an empty library",
        }),
      ],
    }),
  },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const over = await canvas.findByTestId("game-over");
    expect(over.dataset.result).toBe("loss");
    // Each loser says why, which is the difference between a result and a story.
    expect(over.textContent).toContain("commander damage");
    await userEvent.click(await canvas.findByText(/Rematch/i));
    expect(args.onRematch).toHaveBeenCalled();
  },
};

/** Not over: the screen is not in the document. */
export const StillPlaying: Story = {
  args: { state: gameView() },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(canvas.queryByTestId("game-over")).toBeNull();
  },
};
