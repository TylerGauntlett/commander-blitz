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
import type { PadButton } from "../../input/buttons";
import { getCursor, setCursor } from "../../input/cursor";
import { getGroup, groupOf } from "../../input/groups";
import { boundButtons, startPad } from "../../input/pad";
import { activeRoot } from "../../input/stops";
import { NAVIGATION_HINTS } from "../../logic/verbs";
import {
  expectCardsSized,
  expectHandheldFloors,
  expectNothingOverflows,
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
  args: board(scenarios.fourPlayerPod()),
  parameters: { automtg: { zoomLock: false } },
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

    await userEvent.click(within(strip).getByRole("button"));
    await waitFor(() => {
      expect(canvasElement.querySelector('[data-testid="viewing-strip"]')).toBeNull();
    });
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
    expectNothingOverflows(canvasElement);
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
    expectNothingOverflows(canvasElement);
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
    expectNothingOverflows(canvasElement);
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
    expectNothingOverflows(canvasElement);
    expectUniqueActionIds(canvasElement);
  },
};

/**
 * The opening hand, on a whole board.
 *
 * `OpeningHand.stories.tsx` mounts that screen on its own; this is the
 * integration the component test cannot make -- the surface, the board it
 * covers, and `ActionPanel` standing down behind it. `expectUniqueActionIds` is
 * the assertion that matters: `keep` and `mulligan` exist once between the two,
 * and the whole reason `ownsDecision` is a wider question than
 * `isModalDecision` is that they would otherwise exist twice.
 */
export const HandheldModalDecision: Story = {
  args: board(scenarios.mulligan()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  parameters: { automtg: { zoomLock: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    // The screen owns it, and the dialog it replaced does not open behind it.
    await canvas.findByTestId("opening-hand");
    expect(canvas.queryByTestId("prompt-dialog")).toBeNull();
    expectHandheldFloors(canvasElement);
    expectNothingOverflows(canvasElement);
    expectUniqueActionIds(canvasElement);
  },
};

/**
 * A board with more permanents than the screen can hold, so the mat scrolls.
 *
 * `.play__mine` is exempted from the fit check here, and it is the one place
 * that exemption is correct: this story exists to pose the overflow, and
 * `board.css` gives the viewer's mat `overflow-y: auto` precisely so a board
 * you have to scroll beats a board you cannot read. Everything ELSE still has
 * to fit -- the foot, the opponents' row, the action panel and the ribbon --
 * which is what a blanket skip would have stopped saying.
 */
export const HandheldCrowdedBoard: Story = {
  args: board(scenarios.crowdedBoard()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  parameters: { automtg: { zoomLock: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    expectHandheldFloors(canvasElement);
    expectNothingOverflows(canvasElement, [".play__mine"]);
  },
};

/**
 * Standing at an opponent's seat.
 *
 * At 1280x800 an opponent's cards are not drawn at all, so "let me actually
 * look at that board" needs an answer -- and the one a pod wants is not a peek
 * but a place: you go and stand at their seat and come back.
 *
 * What this asserts is the rule that makes it safe: **the node moves, it is
 * never copied.** Exactly one box per `data-oid` and one per `data-player`,
 * before and after. Two of either is not a cosmetic problem -- `FxLayer`
 * resolves a damage numeral with `document.querySelector` and would anchor it
 * to whichever came first, and the ring would have two places to be.
 */
export const HandheldViewingAnOpponent: Story = {
  args: board(scenarios.fourPlayerPod()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  parameters: { automtg: { zoomLock: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");

    const counts = () => {
      const oids = [...canvasElement.querySelectorAll("[data-oid]")].map((el) =>
        el.getAttribute("data-oid"),
      );
      const players = [...canvasElement.querySelectorAll("[data-player]")].map((el) =>
        el.getAttribute("data-player"),
      );
      return {
        duplicateOids: oids.filter((id, i) => oids.indexOf(id) !== i),
        duplicatePlayers: players.filter((id, i) => players.indexOf(id) !== i),
      };
    };

    expect(counts().duplicateOids, "before").toEqual([]);
    expect(counts().duplicatePlayers, "before").toEqual([]);

    await userEvent.click(await canvas.findByTestId("player-1"));

    const strip = await canvas.findByTestId("viewing-strip");
    expect(strip.textContent).toContain("Viewing");
    // Their lanes are here, and their seat says it is the one you are at.
    expect(canvasElement.querySelector('.play__mine[data-viewing="1"]')).not.toBeNull();
    expect(canvasElement.querySelector(".seat--viewing")).not.toBeNull();

    expect(counts().duplicateOids, "while viewing").toEqual([]);
    expect(counts().duplicatePlayers, "while viewing").toEqual([]);

    // The strip carries the way back, and it is not an action id: coming home
    // is not a move in the game.
    expect(strip.querySelector("[data-action-id]")).toBeNull();
    await userEvent.click(within(strip).getByRole("button"));
    await waitFor(() => {
      expect(canvasElement.querySelector('[data-testid="viewing-strip"]')).toBeNull();
    });
  },
};

/**
 * Pressing a seat you are aiming at targets it, and does not wander off.
 *
 * The ordering is the whole rule: a press that could be either has to be the
 * game move. An attacker that silently opened a board viewer mid-combat would
 * be the worst kind of surprise.
 */
export const HandheldSeatPressTargetsFirst: Story = {
  args: board(scenarios.combatDeclareAttackers()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  parameters: { automtg: { zoomLock: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");

    /*
     * Pick one of YOUR creatures, then point it at a seat. That press must
     * stage the attack rather than take you to their board.
     *
     * Scoped to `.play__mine`: the first `[data-oid]` in the document is an
     * opponent's, and on a handheld theirs are clipped to zero height with
     * `pointer-events: none` -- which is the layout working, and would have
     * made this story fail for a reason that has nothing to do with what it
     * asserts.
     */
    const attacker = canvasElement.querySelector(".play__mine [data-oid]") as HTMLElement;
    await userEvent.click(attacker);
    await userEvent.click(await canvas.findByTestId("player-1"));

    expect(canvasElement.querySelector('[data-testid="viewing-strip"]')).toBeNull();
  },
};

/**
 * EVERY BUTTON THE HINT BAR ADVERTISES ACTUALLY DOES SOMETHING.
 *
 * The bar has advertised `L1 Zone` and `L2 Menu` since it was written, and
 * `verbsFor` returns `Y Read` on every card stop -- and for several rounds
 * **nothing in the app listened for any of the three**. An advertised button
 * that does nothing is worse than an unadvertised one: it teaches the player
 * that the bar is not to be trusted.
 *
 * Nothing in the suite could see it, either, because the bar renders spans and
 * a span cannot fail to work. So this mounts the real board and compares what
 * the bar can SAY against what `pad.ts` has a listener for.
 */
export const EveryAdvertisedButtonIsBound: Story = {
  args: board(scenarios.earlyBoard()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");

    const bound = new Set(boundButtons());

    // The navigation half, which the bar draws unconditionally.
    for (const hint of NAVIGATION_HINTS) {
      if (hint.btn === "dpad") continue; // four bindings, and `useCursorNav` owns them.
      expect(bound.has(hint.btn as PadButton), `${hint.btn} is advertised`).toBe(true);
    }

    /*
     * ...and the verbs, which change with the stop.
     *
     * `A` and the four directions are deliberately not here: `useCursorNav`
     * binds those, and it is mounted by `Screen` rather than by the board, so a
     * story that renders `Table` alone would be asserting the absence of a
     * component it never mounted. `e2e/pad.spec.ts` owns them -- "the d-pad
     * walks the ring and A presses what it is on" -- against the real app.
     *
     * What is left is exactly the set this board is responsible for, which is
     * also the set that was advertised and unbound.
     */
    for (const btn of ["b", "x", "y", "r1"] as PadButton[]) {
      expect(bound.has(btn), `${btn} is a verb the bar can print`).toBe(true);
    }
  },
};

/**
 * Stepping between the board's regions, and the trap that follows.
 *
 * Directional navigation crosses a 96px seat strip, three lanes, a fanned hand
 * and a 243px rail one card at a time. `docs/handheld-playtest.md` Loop 1
 * records walking the board as "a bad way to ask can you reach everything":
 * reachable and reachable-in-under-a-second are different properties, and only
 * the second is playable.
 *
 * `[` and `]` are what `input/buttons.ts` maps to `L1` and `R1` on a keyboard,
 * which is the only route a test has into the pad -- neither Playwright nor
 * Vitest can synthesise a real Gamepad.
 *
 * `startPad()` because the key latch lives in `input/pad.ts` and `useCursorNav`
 * is what starts it in the app -- and that is mounted by `Screen`, not by the
 * board. A story that rendered `Table` alone would be asserting the absence of
 * a component it never mounted.
 */
export const HandheldRegionStepping: Story = {
  args: board(scenarios.earlyBoard()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    startPad();

    const region = () => document.documentElement.getAttribute("data-group");

    /*
     * It is already in the hand, and that is the OTHER half of this feature.
     *
     * `earlyBoard` is your main phase with something castable, and
     * `groupForDecision` says a main phase is spent deciding what to play -- so
     * the ring has been put where the decision is before a button was touched.
     */
    await waitFor(() => expect(region()).toBe("hand"));
    const first = region();

    await userEvent.keyboard("]");
    await waitFor(() => expect(region()).not.toBe(first));

    // ...and back again, which is what makes it a step rather than a cycle you
    // have to go the long way round.
    //
    // `[[` and not `[`: a bare bracket opens a key descriptor in `userEvent`'s
    // grammar, so the literal has to be doubled.
    await userEvent.keyboard("[[");
    await waitFor(() => expect(region()).toBe(first));

    /*
     * The ring is inside the region it names.
     *
     * This is the trap, and it is the reason a region is a container rather
     * than a stop-id prefix: `card:<oid>` is a hand card AND a board card AND a
     * stack item, so only the DOM can say which one the ring is on.
     */
    const cursor = document.querySelector("[data-cursor]");
    expect(cursor, "the ring landed somewhere").not.toBeNull();
    expect(groupOf(cursor as Element)).toBe(first);
  },
};

/**
 * `Y` reads the card the ring is on, full screen.
 *
 * The rail's reader carries name, cost, type, P/T and rules at 16px, which is
 * what a player needs most of the time and is why it is worth 236px of the
 * rail. This is the deeper read -- a card with six lines of rules, or one whose
 * art is how you will recognise it next turn.
 *
 * `i` is `Y` on a keyboard (`input/buttons.ts`).
 */
export const HandheldCardHold: Story = {
  args: board(scenarios.earlyBoard()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    startPad();

    // Onto a card, wherever the decision rule left the ring.
    await waitFor(() => {
      expect(document.querySelector("[data-cursor]")).not.toBeNull();
    });

    await userEvent.keyboard("i");
    const hold = await canvas.findByTestId("card-hold");

    // The same `variant="big"` the desktop rail draws. The roadmap's rule for
    // this round is that the card sizes are fine as they are; what changes is
    // which one is used where.
    expect(hold.querySelector(".card--big")).not.toBeNull();
    // It traps the ring, so it cannot wander the board underneath a full-screen
    // overlay while the player cannot see where it has gone.
    expect(hold.hasAttribute("data-modal-root")).toBe(true);

    // `B` puts it down.
    await userEvent.keyboard("{Escape}");
    await waitFor(() => {
      expect(canvasElement.querySelector('[data-testid="card-hold"]')).toBeNull();
    });
  },
};

/**
 * Holding `L2` jumps straight to a region instead of cycling to it.
 *
 * `L1`/`R1` step, which is right at two or three regions and wearing at five --
 * getting from the hand to the board is three presses and a guess about which
 * direction is shorter.
 *
 * ON THE TRIGGER AND NOT ON A SHOULDER, and that is not a preference. `pad.ts`
 * reports PRESSES and has no release event for a shoulder, so a hold there is a
 * timer with nothing to cancel it: a tap would open the dial 260ms later,
 * having already stepped. A trigger is analog and `onFrame` reports its
 * position every frame, which is the same channel the `R2` opponent reader is
 * held on. `z` is `L2` on a keyboard (`input/buttons.ts`).
 */
/**
 * `L2` TAPPED SENDS THE RING TO THE THING THAT ENDS THE DECISION.
 *
 * The commit slab -- Attack, Block, Done, Pass -- lives in the right rail, and
 * on a 1280x800 panel the ring is almost never near it: you are in your hand,
 * or out on an opponent's board choosing what to swing at, and the rail is the
 * far corner. Walking there is a dozen presses across a seat strip, three lanes
 * and a fanned hand; `R1` is two steps if you happen to know the region order.
 * Neither is a thing to ask for once a phase, thirteen phases a turn.
 *
 * The button was already advertised. It said `Jump`, and it jumped to the tool
 * strip -- which `Menu` also did, so the one shoulder the bar promises was
 * spent on the second way to reach the settings menu.
 *
 * A TAP, not a hold: holding `L2` still opens the region dial, and the two do
 * not collide because a tap crosses and releases the analog threshold inside a
 * frame or two. `HandheldRegionDial` above is the other half of the same
 * button.
 */
/**
 * THE COMMAND ZONE IS SOMEWHERE THE RING CAN GO.
 *
 * It was not, and it was the only control on the board that was not. The board
 * declares its stops explicitly -- `stopsIn` takes a surface at its word and
 * gives it no native-focusable fallback -- and the commander plinth is a
 * `<button>` carrying no `data-stop`, so the ring could not reach it by any
 * route. A controller could not cast its own commander at all, and the plinth's
 * documented promise that "the full card is one hover away in the preview rail"
 * held for a mouse and for nothing else: `hoverFor` drives `hoveredOid` from
 * the cursor, and the cursor could not get here.
 *
 * The plinth carries `card:<oid>` while the commander is in the command zone,
 * which is the same id the board would use for it and the reason everything
 * else follows for nothing: `A` casts, `Y` reads, and the rail fills.
 */
export const HandheldTheCommanderIsReachable: Story = {
  args: board(scenarios.earlyBoard()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    startPad();

    const plinth = canvasElement.querySelector<HTMLElement>('[data-testid^="commander-"]');
    expect(plinth, "the scenario needs a commander in the command zone").not.toBeNull();
    const stop = plinth?.dataset.stop;
    expect(stop, "the plinth has to declare a stop or the ring cannot see it").toBeTruthy();

    // Walked to, not placed: what was broken is that no route arrived here.
    for (let i = 0; i < 6 && getGroup() !== "orb"; i += 1) {
      await userEvent.keyboard("]");
      await waitFor(() => expect(getCursor()).not.toBeNull());
    }
    expect(getGroup()).toBe("orb");
    setCursor(stop as string);
    expect(getCursor()).toBe(stop);

    // ...and the rail read it, which is the whole point of being able to.
    await waitFor(() => {
      const rail = canvasElement.querySelector('[data-testid="card-preview"]');
      expect(rail?.textContent).toContain("Aesi");
    });
  },
};

/** The element the ring is on, which is `[data-cursor]` and nothing else. */
function ringed(root: HTMLElement): HTMLElement {
  const el = root.querySelector<HTMLElement>("[data-cursor]");
  if (!el) throw new Error("the ring is not on anything");
  return el;
}

export const HandheldJumpToTheDecision: Story = {
  args: board(scenarios.combatDeclareAttackers()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    startPad();

    const dock = canvasElement.querySelector(".commit-dock");
    expect(dock, "the scenario has to have a slab for this to be about").not.toBeNull();

    // Somewhere else entirely first, which is the case this exists for.
    await userEvent.keyboard("]");
    await waitFor(() => expect(groupOf(ringed(canvasElement))).not.toBe("acts"));

    // `z` is `L2`; native events for the reason `HandheldRegionDial` explains.
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "z", bubbles: true }));
    window.dispatchEvent(new KeyboardEvent("keyup", { key: "z", bubbles: true }));

    await waitFor(() => {
      const on = ringed(canvasElement);
      expect(dock?.contains(on), `ring landed on ${on?.getAttribute("data-testid")}`).toBe(
        true,
      );
    });
    // ...and the region trap came with it, or the next direction press would
    // walk straight back out of the rail.
    expect(groupOf(ringed(canvasElement))).toBe("acts");
  },
};

export const HandheldRegionDial: Story = {
  args: board(scenarios.earlyBoard()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    startPad();

    /*
     * Native events rather than `userEvent`, and it is worth saying why.
     *
     * `pad.ts` listens on `window`, and `userEvent`'s press-and-hold grammar
     * (`{z>}` / `{/z}`) keeps its held-key state per SESSION -- two separate
     * `userEvent.keyboard()` calls are two sessions, so the release refers to a
     * key the second one never pressed and no `keyup` is dispatched at all. The
     * hold then never ends and the story fails on a detail of the test library
     * rather than on the app.
     */
    const key = (type: "keydown" | "keyup") =>
      window.dispatchEvent(new KeyboardEvent(type, { key: "z", bubbles: true }));

    key("keydown");
    const dial = await canvas.findByTestId("group-dial");

    /*
     * `.wheelwrap` is the contract, not decoration. `input/stops.ts`'s trap has
     * preferred that class over every other candidate since it was written and
     * nothing in the repo has ever rendered one -- it was the prototype's name
     * for exactly this control, carried into the trap and then not built. So
     * the ring is inside the dial the moment it opens, with no change to the
     * trap at all.
     */
    expect(dial.classList.contains("wheelwrap")).toBe(true);
    expect(activeRoot()).toBe(dial);

    // A spoke per region that is actually there, and none of them is an action.
    expect(dial.querySelectorAll(".wheel__spoke").length).toBeGreaterThan(1);
    expect(dial.querySelector("[data-action-id]")).toBeNull();

    // Letting go puts it away -- which is the whole argument for a hold over a
    // toggle: you cannot forget to release.
    key("keyup");
    await waitFor(() => {
      expect(canvasElement.querySelector('[data-testid="group-dial"]')).toBeNull();
    });
  },
};
