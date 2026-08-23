/**
 * The whole board.
 *
 * These are the stories that prove the harness. Every other component can look
 * plausible in a box; `Table` is the one whose correctness *is* its geometry --
 * the zoom solver measures three grid tracks, the hand fans against
 * `--card-w-base`, and the lanes band by distance from the player they belong
 * to. If this renders at sane card sizes, the cascade reached the canvas.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, waitFor, within } from "storybook/test";
import {
  expectCardsSized,
  expectHandheldFloors,
  expectUniqueActionIds,
} from "../../testing/asserts";
import { fakeGame, idleMutation } from "../../testing/fakeGame";
import type { Scenario } from "../../testing/scenarios";
import * as scenarios from "../../testing/scenarios";
import { Table } from "./Table";

/** A scenario, wired into the props `Table` takes. */
function board(scenario: Scenario, game = {}) {
  return {
    session: { gameId: "story", seat: 0 },
    state: scenario.state,
    game: fakeGame({ state: scenario.state, actions: scenario.actions, ...game }),
    onQuit: fn(),
    onRematch: fn(),
  };
}

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
 * down, so the mulligan buttons exist exactly once between them rather than
 * once each.
 */
export const ModalDecision: Story = {
  args: board(scenarios.mulligan()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const dialog = await canvas.findByTestId("prompt-dialog");
    expect(dialog.dataset.decisionKind).toBe("mulligan");
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
 * A gesture that must *not* reach the server.
 *
 * The other half of `PlayingALand`. Mind Stone offers two abilities and one of
 * them sacrifices it, so the click that means "what can this do?" has to hand
 * the choice to the panel instead of resolving it. Before the engine offered
 * both, the artifact had a single action and this click deleted it.
 */
export const ChoosingBetweenTwoAbilities: Story = {
  args: board(scenarios.twoAbilityPermanent(), { act: idleMutation(fn()) }),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");

    const stone = await canvas.findByTestId("card-401");
    await userEvent.click(stone);
    expect(args.game.act.mutate, "clicking the artifact spent it").not.toHaveBeenCalled();
    expect(stone.className).toContain("card--selected");

    // Both abilities are reachable, on their own controls.
    for (const id of ["a1-activate", "a2-activate"]) {
      expect(
        canvasElement.querySelector(`[data-action-id="${id}"]`),
        `the panel never rendered ${id}`,
      ).not.toBeNull();
    }
    expectUniqueActionIds(canvasElement);

    // And the click is reversible. Neither ability targets anything, so this is
    // a selection rather than a target hunt -- entering targeting mode here
    // would leave the player with nothing to click and no way back out.
    await userEvent.click(stone);
    expect(stone.className).not.toContain("card--selected");
  },
};

/* ------------------------------------------------------------------ */
/* The zoom, deliberately unlocked                                     */
/* ------------------------------------------------------------------ */

/**
 * The half of the zoom that pure tests cannot reach.
 *
 * `tests/zoomFit.test.ts` covers the solver as a function. What it cannot cover
 * is the measuring: whether the three grid tracks report real sizes and whether
 * the solved width is written back where the cards can see it. That needs a
 * browser, and it needs the feature switched on -- every other story pins it,
 * for the same reason `e2e/helpers.ts` does.
 */
export const ZoomCrowdedBoard: Story = {
  args: board(scenarios.crowdedBoard()),
  parameters: { automtg: { zoomLock: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const table = await canvas.findByTestId("table");
    const zoom = Number.parseFloat(table.getAttribute("data-zoom-board") ?? "0");
    expect(zoom, "the solver never reported a board scale").toBeGreaterThan(0);
    expectCardsSized(canvasElement, ".lane .card");
  },
};

export const ZoomFifteenCardHand: Story = {
  args: (() => {
    const scenario = scenarios.openingHand();
    // Eight more cards than the fan was designed around, which is the crowded
    // branch of `solveHandCardWidth`.
    const hand = scenario.state.players[0].hand ?? [];
    const crowded = Array.from({ length: 15 }, (_, i) => ({
      ...hand[i % hand.length],
      oid: 500 + i,
    }));
    scenario.state.players[0].hand = crowded;
    scenario.state.players[0].hand_count = crowded.length;
    return board(scenario);
  })(),
  parameters: { automtg: { zoomLock: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const table = await canvas.findByTestId("table");
    expect(canvasElement.querySelectorAll(".hand .card")).toHaveLength(15);
    const zoom = Number.parseFloat(table.getAttribute("data-zoom-hand") ?? "0");
    expect(zoom, "the hand solver never reported a scale").toBeGreaterThan(0);
  },
};

/**
 * THE RAIL RUNS THE FULL HEIGHT, and the foot sits beside it.
 *
 * This is the structural claim of the whole round, so it is asserted rather
 * than looked at. The rail used to stop where the hand started, because the
 * foot spanned the full width beneath both rails -- 514px at 1280x800, of
 * which the action list, the rows a turn is actually spent in, got 172.
 * `mockups/handheld-board/measure.mjs` measures the same rail at 748 when it
 * runs to the bottom edge instead.
 *
 * `zoomLock: false` deliberately, and it is the point of this story rather than
 * a detail: a pinned zoom asserts the ratios the layout was DESIGNED at, and
 * what has to be true here is that the solver, given a pod and a foot that has
 * moved inside the board's column, still packs everything inside the screen.
 * A pinned story cannot fail that, which is why the pinned pod story above is
 * not the one carrying this assertion.
 */
export const FullHeightRail: Story = {
  args: board(scenarios.fourPlayerPod()),
  parameters: { automtg: { zoomLock: false } },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const table = await canvas.findByTestId("table");

    /*
     * WAIT FOR THE SOLVE, or this gate passes against a board that has not
     * finished laying out.
     *
     * `useZoomFit` runs off a `ResizeObserver`, so at `findByTestId` time the
     * cards are at their initial size and nothing has overflowed yet. The first
     * version of this story asserted there and passed while the settled board
     * was 90px over -- which is worse than no assertion, because it is one that
     * reports the layout is fine.
     */
    await waitFor(() => {
      expect(table.getAttribute("data-zoom-board")).toBeTruthy();
    });
    let last = "";
    for (let i = 0; i < 60; i += 1) {
      await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
      const now = `${table.dataset.zoomBoard}|${table.dataset.zoomPod}|${table.dataset.zoomHand}`;
      if (now === last && i > 4) break;
      last = now;
    }

    const box = (sel: string) => {
      const el = canvasElement.querySelector(sel);
      if (!el) throw new Error(`no ${sel}`);
      return el.getBoundingClientRect();
    };

    const rail = box(".rail--right");
    const play = box(".play");
    const foot = box(".table__foot");

    // It starts where the board starts and ends where the foot ends. Both, or
    // it is a rail that stops somewhere and the 234px is not real.
    expect(Math.abs(rail.top - play.top), "the rail should start with the board").toBeLessThan(
      2,
    );
    expect(Math.abs(rail.bottom - foot.bottom), "the rail should reach the foot").toBeLessThan(
      2,
    );

    // The foot is the board's width, not the screen's -- which is what the fan
    // has to be solved against. See `useZoomFit`'s `footW`.
    expect(foot.right).toBeLessThanOrEqual(rail.left + 1);

    /*
     * And nothing has been pushed off the bottom to pay for it.
     *
     * `scrollHeight > clientHeight` asks the question directly. It is the check
     * `e2e/deckfit.spec.ts` runs against a real engine; this is the same
     * question asked of a component, in CI, where the e2e suite does not run.
     */
    for (const sel of [".play__mine", ".play__opponents", ".table__foot", ".acts"]) {
      const el = canvasElement.querySelector(sel) as HTMLElement;
      expect(el.scrollHeight - el.clientHeight, `${sel} overflows`).toBeLessThanOrEqual(2);
    }
  },
};

/* ------------------------------------------------------------------ handheld
 *
 * The same board, at the layout a Steam Deck gets. Flip the **Layout** toolbar
 * on any story above to compare; these are pinned so the compact arrangement is
 * reviewed deliberately rather than only when somebody remembers to switch.
 *
 * What to look at, in order: the left rail is gone and the stack has moved to
 * the top of the right one; an opponent is a strip rather than a board; the
 * viewer's own cards hold the 96px floor even when that means the mat scrolls.
 *
 * ## Every one of these is a CI gate, and that is new
 *
 * `tags: ["handheld"]` puts them in the `storybook-handheld` project as well as
 * the ordinary one, so each runs twice: at 1600x950, where `data-handheld`
 * gives the compact STRUCTURE with desktop tokens, and at a real 1280x800,
 * where `handheld.css`'s media query also re-values `--rail-r`, `--mat-side`,
 * `--pod-seat-h` and `--hand-lift`. Both have to hold.
 *
 * The floors -- 16px of type, 44px of target, 96px of card -- have been
 * asserted by `e2e/handheldAssert.ts` since Loop 3, but **Playwright is not in
 * CI**, so nothing has ever stopped a change putting a label back under the
 * floor. `scripts/verify.py` does run these. That is what `expectHandheldFloors`
 * is for, and it is the reason these stories stopped being review-only.
 *
 * `zoomLock: false` on every one of them, deliberately: a pinned zoom asserts
 * the designed ratios rather than the solve, and the card floor is a claim
 * about what the solver actually does with the room it has.
 */

/** Your turn, a few lands down. The everyday case. */
export const HandheldBoard: Story = {
  args: board(scenarios.earlyBoard()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  parameters: { automtg: { zoomLock: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    expectHandheldFloors(canvasElement);
  },
};

/**
 * The state that decides whether any of this works.
 *
 * Four seats and full boards at 1280x800 is where the 96px card floor and the
 * opponent strip either earn their place or do not.
 */
export const HandheldPod: Story = {
  args: board(scenarios.fourPlayerPod()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  parameters: { automtg: { zoomLock: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    expectHandheldFloors(canvasElement);
  },
};

/** Combat, where the ring has the most to reach and the least room to do it. */
export const HandheldDeclareAttackers: Story = {
  args: board(scenarios.combatDeclareAttackers()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  parameters: { automtg: { zoomLock: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    expectHandheldFloors(canvasElement);
    expectUniqueActionIds(canvasElement);
  },
};

export const HandheldDeclareBlockers: Story = {
  args: board(scenarios.combatDeclareBlockers()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  parameters: { automtg: { zoomLock: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    expectHandheldFloors(canvasElement);
    expectUniqueActionIds(canvasElement);
  },
};

/** A modal decision, which owns the ring while it is up. */
export const HandheldModalDecision: Story = {
  args: board(scenarios.mulligan()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  parameters: { automtg: { zoomLock: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    expectHandheldFloors(canvasElement);
    expectUniqueActionIds(canvasElement);
  },
};

/** A board with more permanents than the screen can hold, so the mat scrolls. */
export const HandheldCrowdedBoard: Story = {
  args: board(scenarios.crowdedBoard()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  parameters: { automtg: { zoomLock: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    expectHandheldFloors(canvasElement);
  },
};
