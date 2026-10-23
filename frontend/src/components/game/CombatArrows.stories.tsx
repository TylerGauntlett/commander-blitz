/**
 * Who is hitting whom, drawn as curves over the board.
 *
 * This component cannot exist in jsdom at all. Every arrow is measured: it finds
 * its endpoints by querying `data-oid` / `data-player` / `data-stack-sid` in the
 * DOM and resolving their positions relative to a board element. With no layout
 * every anchor is at the origin and every arrow is zero length, so the whole
 * file would pass while drawing nothing.
 *
 * So the stories render a real board underneath -- `PlayerMat` for the anchors,
 * with the overlay on top -- rather than the arrows alone.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { useRef } from "react";
import { expect, waitFor } from "storybook/test";
import type { GameView } from "../../api/types";
import { CARD_SCALE, opponentCardScale } from "../../logic/cardSize";
import { stagedAs, stagedSet } from "../../logic/staging";
import { seatOrder } from "../../logic/zoneGrouping";
import { useUiStore } from "../../state/uiStore";
import * as scenarios from "../../testing/scenarios";
import { CombatArrows } from "./CombatArrows";
import { PlayerMat } from "./PlayerMat";

/**
 * A board with anchors in it.
 *
 * The arrows resolve their endpoints out of this markup, so the mats are not
 * decoration -- without them there is nothing to point at.
 */
function Board({ state }: { state: GameView }) {
  const boardRef = useRef<HTMLDivElement>(null);
  const order = seatOrder(state);
  const opponents = order.filter((pid) => pid !== state.seat);

  return (
    <div ref={boardRef} className="play" style={{ position: "relative", padding: "1rem" }}>
      <div className="play__opponents">
        {opponents.map((pid) => (
          <PlayerMat
            key={pid}
            state={state}
            player={state.players[pid]}
            compact
            // Their lands against their own edge, so the creature bands meet in
            // the middle -- which is also where the arrows have to cross.
            mirrored
            cardScale={opponentCardScale(opponents.length)}
            actionableOids={new Set()}
          />
        ))}
      </div>
      <PlayerMat
        state={state}
        player={state.players[state.seat]}
        cardScale={CARD_SCALE.own}
        actionableOids={new Set()}
      />
      <CombatArrows state={state} boardRef={boardRef} />
    </div>
  );
}

const meta = {
  title: "Game/CombatArrows",
  component: CombatArrows,
  parameters: { commanderblitz: { mount: "tableBody" } },
} satisfies Meta<typeof CombatArrows>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Nothing in combat: the overlay draws no arrows at all. */
export const NoCombat: Story = {
  args: { state: scenarios.earlyBoard().state, boardRef: { current: null } },
  render: () => <Board state={scenarios.earlyBoard().state} />,
  play: async ({ canvasElement }) => {
    await waitFor(() => expect(canvasElement.querySelectorAll(".arrow")).toHaveLength(0));
  },
};

/**
 * Attackers staged but not yet declared.
 *
 * Staging lives entirely in the UI store -- it is a gesture, not a rule -- and
 * the arrows are how it is visible before anything is submitted.
 */
export const StagedAttacks: Story = {
  args: { state: scenarios.combatDeclareAttackers().state, boardRef: { current: null } },
  parameters: {
    commanderblitz: { ui: { staged: stagedSet("attack", { 301: 1, 302: 2 }) } },
  },
  render: () => <Board state={scenarios.combatDeclareAttackers().state} />,
  play: async ({ canvasElement }) => {
    expect(stagedAs(useUiStore.getState().staged, "attack")).toEqual({ 301: 1, 302: 2 });

    // Arrows are measured after layout, so they arrive a frame late.
    await waitFor(
      () => {
        const arrows = [...canvasElement.querySelectorAll("path.arrow, .arrow path, .arrow")];
        expect(arrows.length, "no arrows were drawn for two staged attackers").toBeGreaterThan(
          0,
        );
      },
      { timeout: 3000 },
    );
  },
};

/** Blockers staged against declared attackers. */
export const StagedBlocks: Story = {
  args: { state: scenarios.combatDeclareBlockers().state, boardRef: { current: null } },
  parameters: {
    commanderblitz: { ui: { staged: stagedSet("block", { 401: 410, 402: 411, 403: 412 }) } },
  },
  render: () => <Board state={scenarios.combatDeclareBlockers().state} />,
};

/** Declared combat, straight from the engine rather than from staging. */
export const DeclaredCombat: Story = {
  args: { state: scenarios.combatDeclareBlockers().state, boardRef: { current: null } },
  render: () => <Board state={scenarios.combatDeclareBlockers().state} />,
};

/** Four seats: arrows have to cross the table without pointing at the wrong mat. */
export const FourPlayerCross: Story = {
  args: { state: scenarios.fourPlayerPod().state, boardRef: { current: null } },
  parameters: {
    commanderblitz: { ui: { staged: stagedSet("attack", { 603: 3 }) } },
  },
  render: () => <Board state={scenarios.fourPlayerPod().state} />,
};

/**
 * ONE BOARD ON SCREEN: an attack from a board you cannot see is drawn from
 * their seat.
 *
 * On a handheld an opponent's lanes are clipped to zero height and every card
 * in them still reports a box, so four attackers drew four arrows from four
 * phantom points under the seat strip. A hidden card's end is its controller's
 * `[data-player]` now, and four links to the same pair of elements are one
 * arrow: seat to orb.
 */
export const HandheldHiddenAttackers: Story = {
  args: { state: scenarios.combatDeclareBlockers().state, boardRef: { current: null } },
  globals: { handheld: "on" },
  tags: ["handheld"],
  render: () => <Board state={scenarios.combatDeclareBlockers().state} />,
  play: async ({ canvasElement }) => {
    await waitFor(
      () => {
        const arrows = [...canvasElement.querySelectorAll<SVGPathElement>("path.arrow")];
        expect(arrows, "four hidden attackers are one arrow").toHaveLength(1);
        const start = /^M ([\d.]+) ([\d.]+)/.exec(arrows[0].getAttribute("d") ?? "");
        expect(start).not.toBeNull();
        if (!start) return;
        const board = canvasElement.querySelector(".play") as HTMLElement;
        const origin = board.getBoundingClientRect();
        const seat = canvasElement.querySelector('[data-player="1"]') as HTMLElement;
        const box = seat.getBoundingClientRect();
        const x = Number(start[1]) + origin.left;
        const y = Number(start[2]) + origin.top;
        expect(x, "the arrow starts inside their seat").toBeGreaterThanOrEqual(box.left);
        expect(x).toBeLessThanOrEqual(box.right);
        expect(y).toBeGreaterThanOrEqual(box.top);
        expect(y).toBeLessThanOrEqual(box.bottom);
      },
      { timeout: 3000 },
    );
  },
};
