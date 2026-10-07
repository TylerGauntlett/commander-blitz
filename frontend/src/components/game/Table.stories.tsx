/**
 * The whole board.
 *
 * These are the stories that prove the harness. Every other component can look
 * plausible in a box; `Table` is the one whose correctness *is* its geometry --
 * the zoom solver measures three grid tracks, the hand fans against
 * `--card-w-base`, and the lanes band by distance from the player they belong
 * to. If this renders at sane card sizes, the cascade reached the canvas.
 */

// The zoom, the handheld layout and the controller have files of their own:
// `TableZoom.stories.tsx`, `TableHandheld.stories.tsx`, `TablePad.stories.tsx`.

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { expectCardsSized, expectUniqueActionIds } from "../../testing/asserts";
import { board } from "../../testing/board";
import { idleMutation } from "../../testing/fakeGame";
import * as scenarios from "../../testing/scenarios";
import { Table } from "./Table";

const meta = {
  title: "Game/Table",
  component: Table,
  parameters: { automtg: { mount: "screen" } },
} satisfies Meta<typeof Table>;

export default meta;
type Story = StoryObj<typeof meta>;

export const OpeningHand: Story = {
  args: board(scenarios.openingHand()),

  /*
   * The harness's own test.
   *
   * Nothing here is about the board's behaviour -- it is about whether the
   * cascade reached the canvas at all. If `#storybook-root` has no height, or
   * `theme.css` did not load, or `@property --card-w-base` failed to register,
   * the symptom is identical in every case: `useZoomFit` measures nothing and
   * every card collapses to the solver's 52px floor. That is a board of postage
   * stamps that still passes every content assertion ever written about it, so
   * it gets an assertion of its own.
   */
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");

    const base = Number.parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--card-w-base"),
    );
    expect(base, "--card-w-base must resolve to pixels, not the clamp() text").toBeGreaterThan(
      60,
    );

    expect(canvasElement.querySelectorAll(".hand .card")).toHaveLength(7);
    expectCardsSized(canvasElement, ".hand .card");
    expectUniqueActionIds(canvasElement);
  },
};

export const EarlyBoard: Story = {
  args: board(scenarios.earlyBoard()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    expectUniqueActionIds(canvasElement);
  },
};

export const DeclareAttackers: Story = {
  args: board(scenarios.combatDeclareAttackers()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    // Three attackers x two defenders is six actions, and the panel must reach
    // all of them without rendering any twice -- the case that only exists
    // because there is more than one legal defender.
    expectUniqueActionIds(canvasElement);
  },
};

export const DeclareBlockers: Story = {
  args: board(scenarios.combatDeclareBlockers()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    expectUniqueActionIds(canvasElement);
  },
};

export const StackThreeDeep: Story = {
  args: board(scenarios.stackThreeDeep()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const stack = await canvas.findByTestId("stack-panel");
    // Top first: the counter and the trigger are above the creature spell.
    expect(stack.textContent).toContain("Rhystic Study");
  },
};

export const FourPlayerPod: Story = {
  args: board(scenarios.fourPlayerPod()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    // Three opponents plus the viewer, each with a life total on screen.
    for (const pid of [0, 1, 2, 3]) {
      expect(canvasElement.querySelector(`[data-testid="life-${pid}"]`)).not.toBeNull();
    }
  },
};

export const CrowdedBoard: Story = {
  args: board(scenarios.crowdedBoard()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    // Twelve basics collapse into two counted piles rather than twelve cards.
    const stacks = canvasElement.querySelectorAll("[data-stack-count]");
    expect(stacks.length).toBeGreaterThan(0);
  },
};

/**
 * A modal owns the decision.
 *
 * The invariant with teeth: the dialog renders the ids and the panel stands
 * down, so a decision's buttons exist exactly once between them rather than
 * once each.
 */
export const ModalDecision: Story = {
  args: board(scenarios.mayAbility()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const dialog = await canvas.findByTestId("prompt-dialog");
    expect(dialog.dataset.decisionKind).toBe("may");
    expectUniqueActionIds(canvasElement);
  },
};

/**
 * ...and so does a surface that is not the dialog.
 *
 * `ownsDecision` is a wider question than `isModalDecision` precisely so this
 * holds: the opening hand is not a `PromptDialog` and the panel has to stand
 * down for it anyway. Get that split wrong and `keep` and `mulligan` render
 * twice, once here and once behind it.
 */
export const OpeningHandOwnsTheDecision: Story = {
  args: board(scenarios.mulligan()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const stage = await canvas.findByTestId("opening-hand");
    expect(stage.dataset.decisionKind).toBe("mulligan");
    expect(canvas.queryByTestId("prompt-dialog")).toBeNull();
    expectUniqueActionIds(canvasElement);
  },
};

export const GameOver: Story = {
  args: board(scenarios.gameOver(0)),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const over = await canvas.findByTestId("game-over");
    expect(over.dataset.result).toBe("win");
  },
};

export const Defeat: Story = {
  args: board(scenarios.gameOver(1)),
};

/**
 * A gesture reaching the server.
 *
 * The client never builds an action; it echoes an id back. This is that contract
 * as a test: click the land in hand, and the exact id the engine sent is what
 * goes out.
 */
export const PlayingALand: Story = {
  args: (() => {
    const scenario = scenarios.openingHand();
    return board(scenario, { act: idleMutation(fn()) });
  })(),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");

    // By id, not by label. A row for a card draws the *card* -- "Forest", with
    // its type line -- and never the action's "Play Forest" text, which is the
    // whole point of the grouped list. `data-action-id` is the contract.
    const play = canvasElement.querySelector<HTMLElement>('[data-action-id="a1-play_land"]');
    expect(play, "the panel never rendered the land action").not.toBeNull();
    await userEvent.click(play as HTMLElement);
    expect(args.game.act.mutate).toHaveBeenCalledWith("a1-play_land");
  },
};

/**
 * A gesture that must *not* reach the server by itself.
 *
 * The other half of `PlayingALand`. Mind Stone offers two abilities and one of
 * them sacrifices it, so the click that means "what can this do?" has to ASK
 * instead of resolving. It used to select the card and leave the choice to the
 * panel; on a handheld both panel rows read "Mind Stone: {T}…", so the board
 * now asks in `AbilityMenu` and the chosen item does what the row would.
 */
export const ChoosingBetweenTwoAbilities: Story = {
  args: board(scenarios.twoAbilityPermanent(), { act: idleMutation(fn()) }),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");

    const stone = await canvas.findByTestId("card-401");
    await userEvent.click(stone);
    expect(args.game.act.mutate, "clicking the artifact spent it").not.toHaveBeenCalled();

    const menu = await canvas.findByTestId("ability-menu");
    expect(menu.hasAttribute("data-modal-root"), "the menu traps the ring").toBe(true);
    const items = menu.querySelectorAll("[data-stop^='menu:ability:']");
    expect(items, "one item per ability").toHaveLength(2);
    expect(items[0].textContent).not.toContain("Mind Stone");
    expect(items[1].textContent).toContain("Sacrifice");
    // The items decide; the panel's rows still carry the ids, exactly once.
    expect(menu.querySelector("[data-action-id]")).toBeNull();
    for (const id of ["a1-activate", "a2-activate"]) {
      expect(
        canvasElement.querySelector(`[data-action-id="${id}"]`),
        `the panel never rendered ${id}`,
      ).not.toBeNull();
    }
    expectUniqueActionIds(canvasElement);

    // Choosing the second item posts the second ability and puts the menu away.
    await userEvent.click(canvas.getByTestId("ability-1"));
    expect(args.game.act.mutate).toHaveBeenCalledWith("a2-activate");
    expect(canvasElement.querySelector('[data-testid="ability-menu"]')).toBeNull();
  },
};
