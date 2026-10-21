/**
 * The whole board with the zoom deliberately unlocked: the measuring half of
 * the solver, the full-height rail, and standing at an opponent's seat.
 *
 * Split out of `Table.stories.tsx`, which has the harness's own test.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent, waitFor, within } from "storybook/test";
import { useUiStore } from "../../state/uiStore";
import { expectCardsSized } from "../../testing/asserts";
import { board } from "../../testing/board";
import { card } from "../../testing/fixtures";
import * as scenarios from "../../testing/scenarios";
import { Table } from "./Table";

const meta = {
  title: "Game/Table Zoom",
  component: Table,
  parameters: { commanderblitz: { mount: "screen" } },
} satisfies Meta<typeof Table>;

export default meta;
type Story = StoryObj<typeof meta>;

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
  parameters: { commanderblitz: { zoomLock: false } },
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
  parameters: { commanderblitz: { zoomLock: false } },
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
 * the handheld-board round's measurements (`docs/adr/0013-handheld-floors-are-ci-gates.md`) measures the same rail at 748 when it
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
  parameters: { commanderblitz: { zoomLock: false } },
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
     * The FIT is asserted by the handheld stories below, not here.
     *
     * This one runs with desktop tokens on a 1200x900 tester canvas, which is a
     * configuration the app cannot produce: 1200 is inside
     * `(max-width: 1366px)`, so a real client at that size is a handheld. The
     * relationships above hold at any size and are the claim this story exists
     * for; "and everything still fits" needs a viewport that is really the one
     * being claimed, which is what `expectNothingOverflows` on the handheld
     * stories has. See `vite.config.ts` for why the canvas is not 1600x950.
     */
    expect(canvasElement.querySelector(".rail--left"), "the left rail is retired").toBeNull();
  },
};

/**
 * Standing at an opponent's seat, on a DESKTOP.
 *
 * The swap is not a handheld feature. Pressing a seat is how you read a board
 * at any size, and on a desktop it answers a question the compact layout does
 * not have: at four seats an opponent's cards are drawn at the 52px floor with
 * their lanes scrolling behind a fade, so "let me actually look at that" is
 * still a real thing to want.
 *
 * The rule it exists to prove is the same one: **the node moves, it is never
 * copied**. That is the half a handheld cannot check on its own, because there
 * an opponent's lanes are clipped to zero anyway -- here they are drawn, so a
 * seat that failed to give them up would put two boxes on screen rather than
 * one visible and one invisible.
 */
export const ViewingAnOpponent: Story = {
  args: board(
    (() => {
      // Something in their exile, so the strip offers it beside the graveyard.
      const scenario = scenarios.fourPlayerPod();
      scenario.state.players[1].exile = [
        card({ oid: 9901, name: "Exiled Thing", zone: "exile", controller: 1, owner: 1 }),
      ];
      return scenario;
    })(),
  ),
  parameters: { commanderblitz: { zoomLock: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");

    const boxes = (attr: string) =>
      [...canvasElement.querySelectorAll(`[${attr}]`)].map((el) => el.getAttribute(attr) ?? "");
    const dupes = (list: string[]) => list.filter((id, i) => list.indexOf(id) !== i);

    expect(dupes(boxes("data-oid")), "before").toEqual([]);

    await userEvent.click(await canvas.findByTestId("player-1"));

    const strip = await canvas.findByTestId("viewing-strip");
    expect(strip.textContent).toContain("Viewing");
    expect(canvasElement.querySelector('.play__mine[data-viewing="1"]')).not.toBeNull();

    /*
     * Their own mat kept its seat and gave up its lanes.
     *
     * This is the assertion a handheld cannot make: there the lanes are clipped
     * whether or not the swap took them, so only a desktop can tell "moved"
     * from "hidden twice".
     */
    const theirMat = canvasElement.querySelector('[data-testid="mat-1"]');
    expect(theirMat?.querySelector(".seat"), "their seat stays").not.toBeNull();
    expect(theirMat?.querySelector(".mat__lanes"), "their lanes moved").toBeNull();

    expect(dupes(boxes("data-oid")), "while viewing").toEqual([]);
    expect(dupes(boxes("data-player")), "while viewing").toEqual([]);

    // Your own panel is still there -- life and open mana are most of what you
    // assess a threat against.
    expect(canvasElement.querySelector(".play__mine .mat__side")).not.toBeNull();

    // Their graveyard and exile open from the strip, each as their own peek.
    for (const zone of ["graveyard", "exile"]) {
      await userEvent.click(within(strip).getByTestId(`viewing-${zone}-1`));
      await canvas.findByTestId("zone-peek");
      expect(useUiStore.getState().peek).toEqual({ pid: 1, zone });
      useUiStore.getState().setPeek(null);
      await waitFor(() =>
        expect(canvasElement.querySelector('[data-testid="zone-peek"]')).toBeNull(),
      );
    }

    await userEvent.click(within(strip).getByRole("button", { name: "Back to your board" }));
    await waitFor(() => {
      expect(canvasElement.querySelector('[data-testid="viewing-strip"]')).toBeNull();
    });
  },
};
