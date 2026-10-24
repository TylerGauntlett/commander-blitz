/**
 * The whole board at a Steam Deck's layout. Split out of `Table.stories.tsx`;
 * the controller's half is `TablePad.stories.tsx`.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent, waitFor, within } from "storybook/test";
import { startPad } from "../../input/pad";
import { useUiStore } from "../../state/uiStore";
import {
  expectHandheldFloors,
  expectNothingOverflows,
  expectUniqueActionIds,
} from "../../testing/asserts";
import { board } from "../../testing/board";
import * as scenarios from "../../testing/scenarios";
import { Table } from "./Table";

const meta = {
  title: "Game/Table Handheld",
  component: Table,
  parameters: { commanderblitz: { mount: "screen" } },
} satisfies Meta<typeof Table>;

export default meta;
type Story = StoryObj<typeof meta>;

/* ------------------------------------------------------------------ handheld
 *
 * The same board, at the layout a Steam Deck gets. Flip the **Layout** toolbar
 * on any story in `Table.stories.tsx` to compare; these are pinned so the compact arrangement is
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
  globals: { viewport: { value: "deck" }, input: "pad" },
  tags: ["handheld"],
  parameters: { commanderblitz: { zoomLock: false } },
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
  globals: { viewport: { value: "deck" }, input: "pad" },
  tags: ["handheld"],
  parameters: { commanderblitz: { zoomLock: false } },
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
  globals: { viewport: { value: "deck" }, input: "pad" },
  tags: ["handheld"],
  parameters: { commanderblitz: { zoomLock: false } },
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
  globals: { viewport: { value: "deck" }, input: "pad" },
  tags: ["handheld"],
  parameters: { commanderblitz: { zoomLock: false } },
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
  globals: { viewport: { value: "deck" }, input: "pad" },
  tags: ["handheld"],
  parameters: { commanderblitz: { zoomLock: false } },
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
 * Four artifacts and enchantments on a Steam Deck: the lane fans, it does not wrap.
 *
 * The playtest board. The global lane is a third of the front band, and the
 * third card in it used to start a second row -- the front band grew a card
 * taller and pushed the lands and the viewer's own seat off the bottom of the
 * screen. Now the lane overlaps its cards on one row, so the board fits and
 * nothing in the viewer's seat has scrolled away.
 */
export const HandheldFullGlobalLane: Story = {
  args: board(scenarios.fullGlobalLane()),
  globals: { viewport: { value: "deck" }, input: "pad" },
  tags: ["handheld"],
  parameters: { commanderblitz: { zoomLock: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    const global = await canvas.findByTestId("lane-0-Artifacts-Enchantments");
    await waitFor(() => {
      const tops = [...global.querySelectorAll<HTMLElement>(".cardstack")].map(
        (el) => el.getBoundingClientRect().top,
      );
      expect(tops).toHaveLength(4);
      // One row: every stack starts at the same height.
      expect(Math.max(...tops) - Math.min(...tops)).toBeLessThan(1);
    });
    const mine = canvasElement.querySelector<HTMLElement>(".play__mine");
    const side = canvasElement.querySelector<HTMLElement>(".play__mine .mat__side");
    expect(mine && side).toBeTruthy();
    if (!mine || !side) return;
    // The seat's foot -- life, library, graveyard -- is inside the visible board.
    expect(side.getBoundingClientRect().bottom).toBeLessThanOrEqual(
      mine.getBoundingClientRect().bottom + 1,
    );
    expectHandheldFloors(canvasElement);
    expectNothingOverflows(canvasElement);
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
  globals: { viewport: { value: "deck" }, input: "pad" },
  tags: ["handheld"],
  parameters: { commanderblitz: { zoomLock: false } },
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
  globals: { viewport: { value: "deck" }, input: "pad" },
  tags: ["handheld"],
  parameters: { commanderblitz: { zoomLock: false } },
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
    const orbTopBefore = canvasElement.querySelector(".orb")?.getBoundingClientRect().top;

    await userEvent.click(await canvas.findByTestId("player-1"));

    const strip = await canvas.findByTestId("viewing-strip");
    expect(strip.textContent).toContain("Viewing");
    // Their lanes are here, and their seat says it is the one you are at.
    expect(canvasElement.querySelector('.play__mine[data-viewing="1"]')).not.toBeNull();
    expect(canvasElement.querySelector(".seat--viewing")).not.toBeNull();

    expect(counts().duplicateOids, "while viewing").toEqual([]);
    expect(counts().duplicatePlayers, "while viewing").toEqual([]);

    /*
     * YOUR PANEL DOES NOT MOVE, AND NONE OF IT LEAVES THE SCREEN.
     *
     * The strip used to take a full-width row above both mats, which pushed
     * the orb down by its height -- and on a handheld the side column is sized
     * to the container, so the last row of piles (graveyard, command zone)
     * went below the fold. The strip sits over their lanes only now.
     */
    const orb = canvasElement.querySelector(".orb") as HTMLElement;
    expect(orb.getBoundingClientRect().top, "the orb did not jump").toBe(orbTopBefore);
    const mine = canvasElement.querySelector(".play__mine") as HTMLElement;
    const piles = [...orb.querySelectorAll<HTMLElement>(".pile")];
    expect(piles.length).toBeGreaterThan(0);
    for (const pile of piles) {
      expect(
        pile.getBoundingClientRect().bottom,
        `${pile.textContent} is below the fold`,
      ).toBeLessThanOrEqual(mine.getBoundingClientRect().bottom + 1);
    }

    // The strip carries the way back, and it is not an action id: coming home
    // is not a move in the game.
    expect(strip.querySelector("[data-action-id]")).toBeNull();

    // Their graveyard opens from the strip: the seat has no room to carry it
    // as a control, and a removal spell that has resolved is in there.
    await userEvent.click(within(strip).getByTestId("viewing-graveyard-1"));
    await canvas.findByTestId("zone-peek");
    useUiStore.getState().setPeek(null);
    await waitFor(() =>
      expect(canvasElement.querySelector('[data-testid="zone-peek"]')).toBeNull(),
    );

    await userEvent.click(within(strip).getByRole("button", { name: "Back to your board" }));
    await waitFor(() => {
      expect(canvasElement.querySelector('[data-testid="viewing-strip"]')).toBeNull();
    });
  },
};

/**
 * Holding `R2` (`V` on a keyboard) is the same seat swap, for as long as it is
 * held.
 *
 * It used to draw a copy of their board in an overlay that could only be looked
 * at -- no pointer, no ring, every `data-oid` doubled, and the reader covered.
 * Borrowing the swap gives the hold everything a click on the seat already has.
 */
export const HandheldHoldingR2ViewsAnOpponent: Story = {
  args: board(scenarios.fourPlayerPod()),
  globals: { viewport: { value: "deck" }, input: "pad" },
  tags: ["handheld"],
  parameters: { commanderblitz: { zoomLock: false } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    // The key latch lives in `input/pad.ts`; see `HandheldRegionStepping`.
    startPad();

    // Dispatched by hand: `userEvent.keyboard` keeps held keys per call, so a
    // `{/v}` in a second call releases nothing (see `HandheldRegionDial`).
    const key = (type: "keydown" | "keyup") =>
      window.dispatchEvent(new KeyboardEvent(type, { key: "v", bubbles: true }));
    key("keydown");
    await canvas.findByTestId("viewing-strip");
    expect(canvasElement.querySelector(".play__mine[data-viewing]")).not.toBeNull();
    const oids = [...canvasElement.querySelectorAll("[data-oid]")].map((el) =>
      el.getAttribute("data-oid"),
    );
    expect(
      oids.filter((id, i) => oids.indexOf(id) !== i),
      "while held",
    ).toEqual([]);

    key("keyup");
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
  globals: { viewport: { value: "deck" }, input: "pad" },
  tags: ["handheld"],
  parameters: { commanderblitz: { zoomLock: false } },
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
