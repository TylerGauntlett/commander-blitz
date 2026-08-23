/**
 * A player, as one object.
 *
 * The orb carries the commander plinth, the life seal stamped over its art, the
 * mana row and the zone piles. `tests/playerOrb.test.tsx` covers what it says;
 * what is here is the geometry -- the seal is anchored to where the plinth's art
 * ends, and only the plinth knows where that is.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { useUiStore } from "../../state/uiStore";
import { APP_VAR } from "../../testing/appGeometry";
import { expectMountedLike } from "../../testing/asserts";
import * as pool from "../../testing/cards";
import { gameView, player } from "../../testing/fixtures";
import * as scenarios from "../../testing/scenarios";
import { PlayerOrb } from "./PlayerOrb";

/** The viewer, with a commander and enough board to make mana from. */
function seat(overrides = {}) {
  const state = scenarios.earlyBoard().state;
  return {
    state,
    player: { ...state.players[0], ...overrides },
    isViewer: true,
    isActive: true,
    hasPriority: true,
    names: state.players.map((p) => p.name),
    playableOids: new Set<number>(),
    onSelect: fn(),
    onCastCommander: fn(),
    onHoverCard: fn(),
  };
}

const meta = {
  title: "Game/PlayerOrb",
  component: PlayerOrb,
  parameters: { automtg: { mount: "matSide" } },
} satisfies Meta<typeof PlayerOrb>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Viewer: Story = {
  args: seat(),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const orb = await canvas.findByTestId("player-0");

    /*
     * The orb is its column, and the column is the mat's.
     *
     * `.orb` declares no width at all -- it is `flex: 1 1 auto` inside
     * `.mat__side`, which is a 190px grid track of `.mat`. Rendered without that
     * chain it spans whatever it is given, which is a different design wearing
     * the same class names, and is exactly what this story used to show.
     */
    expectMountedLike(orb, { width: APP_VAR.matSide });

    const life = await canvas.findByTestId("life-0");
    expect(life.textContent).toContain("40");

    /*
     * The seal is stamped over the commander's portrait, and it is only in the
     * right place if it overlaps the plinth. This was a `CMD` badge pinned to a
     * corner once, which at pod size rendered under 3px -- the kind of thing
     * that is correct in the markup and wrong on the screen.
     */
    const plinth = canvasElement.querySelector(".plinth") as HTMLElement;
    if (plinth) {
      const seal = life.getBoundingClientRect();
      const art = plinth.getBoundingClientRect();
      expect(seal.left).toBeGreaterThanOrEqual(art.left - 1);
      expect(seal.right).toBeLessThanOrEqual(art.right + 1);
    }
  },
};

/** An opponent's, in the 112px column a compact mat gives it. */
export const Opponent: Story = {
  args: { ...seat(), isViewer: false, isActive: false, hasPriority: false, compact: true },
  parameters: { automtg: { mount: "matSideCompact" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expectMountedLike(await canvas.findByTestId("player-0"), {
      width: APP_VAR.matSideCompact,
    });
  },
};

export const LowLife: Story = { args: seat({ life: 3 }) };

/**
 * Fifteen from one opponent: past the warning line, six short of lethal.
 *
 * Keyed by the *player* who dealt it, unlike `commander_tax` next to it -- see
 * the note on `PlayerView.commander_damage_taken`. A fixture keyed by commander
 * oid renders a row of honest zeroes and looks completely fine.
 */
export const CommanderDamage: Story = {
  args: seat({ commander_damage_taken: { "1": 15 } }),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const panel = await canvas.findByTestId("cmddmg-0");
    const pip = panel.querySelector('[data-from="1"]') as HTMLElement;
    expect(pip.dataset.amount).toBe("15");
    expect(pip.className, "15 of 21 should be reading as a warning").toContain("cmd-pip--warn");
  },
};

/**
 * The mana row.
 *
 * `total` is an upper bound, not a promise: two sources that each read "{G} or
 * {U}" make two mana but never two of the same colour. The row shows the
 * sources; affordability comes from the action list.
 */
export const ManaRow: Story = {
  args: seat(),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const mana = await canvas.findByTestId("mana-0");
    expect(mana.querySelectorAll(".pip").length).toBeGreaterThan(0);
  },
};

/**
 * What a hovered spell would eat.
 *
 * `spending` is the engine's own solved payment, not arithmetic on the row --
 * `earlyBoard`'s Thragtusk names five sources.
 */
export const ManaRowSpending: Story = {
  args: { ...seat(), spending: new Set([201, 202, 203, 204, 206]) },
};

export const Targetable: Story = {
  args: { ...seat(), targetable: true },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByTestId("player-0"));
    expect(args.onSelect).toHaveBeenCalledWith(0);
  },
};

/** Clicking a zone pile opens the viewer on it. */
export const ZoneCounts: Story = {
  args: (() => {
    const state = scenarios.fullZones().state;
    return {
      state,
      player: state.players[0],
      isViewer: true,
      isActive: true,
      hasPriority: true,
      names: state.players.map((p) => p.name),
      playableOids: new Set<number>(),
      onSelect: fn(),
      onCastCommander: fn(),
      onHoverCard: fn(),
    };
  })(),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const pile = await canvas.findByTestId("pile-0-graveyard");
    expect(pile.textContent).toContain("4");
    await userEvent.click(pile);
    expect(useUiStore.getState().peek).toEqual({ pid: 0, zone: "graveyard" });
  },
};

/** No commander anywhere visible: the seal gets a row of its own. */
export const NoCommander: Story = {
  args: (() => {
    const base = seat();
    const state = gameView({
      players: [player({ command: [] }), base.state.players[1]],
    });
    return { ...base, state, player: state.players[0] };
  })(),
};

/** Two commanders, which is a partner pair sharing the plinth. */
export const TwoCommanders: Story = {
  args: (() => {
    const base = seat();
    const state = gameView({
      players: [
        player({ command: [pool.aesi({ oid: 900 }), pool.edgarMarkov({ oid: 901 })] }),
        base.state.players[1],
      ],
    });
    return { ...base, state, player: state.players[0] };
  })(),
};

/** Input gated while narration plays. */
export const Locked: Story = { args: { ...seat(), locked: true } };

/**
 * An opponent, with the summary line that is most of what you read them by.
 *
 * `threatOf` answers the two questions actually being asked across a table --
 * can they kill me, can they stop me -- so the row is worth having at any size.
 * On a handheld it is the whole seat, because their lanes are clipped there.
 */
export const OpponentWithSpine: Story = {
  args: (() => {
    const base = seat();
    return {
      ...base,
      player: base.state.players[1],
      isViewer: false,
      compact: true,
    };
  })(),
  parameters: { automtg: { mount: "matSideCompact" } },
  play: async ({ canvasElement }) => {
    const spine = canvasElement.querySelector(".orb__spine");
    // Present, and saying something rather than rendering an empty row: an
    // opponent with nothing on board is exactly when the line matters most.
    if (!spine) throw new Error("the opponent spine is missing");
    if (!spine.textContent?.trim()) throw new Error("the spine rendered empty");
  },
};

/** Your own seat draws no spine: your board is right in front of you. */
export const ViewerHasNoSpine: Story = {
  args: seat(),
  play: async ({ canvasElement }) => {
    if (canvasElement.querySelector(".orb__spine")) {
      throw new Error("the viewer should not be summarising their own board");
    }
  },
};
