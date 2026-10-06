/**
 * A player, as one object.
 *
 * The orb carries the commander plinth, the life seal stamped over its art, the
 * mana row and the zone piles. `tests/playerOrb.test.tsx` covers what it says;
 * what is here is the geometry -- the seal is anchored to where the plinth's art
 * ends, and only the plinth knows where that is.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { useEffect, useState } from "react";
import { expect, fn, userEvent, waitFor, within } from "storybook/test";
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

export const LowLife: Story = { args: seat({ life: 3 }) };

/**
 * Fifteen taken from one opponent, and this panel says nothing about it.
 *
 * It used to carry a chip per opposing seat with a meter under it: the loudest
 * object in the column, answering only "how close is each of them to killing
 * me" and nothing about the other direction. Both directions are two arrows on
 * that opponent's own life bar now -- see `OpponentSeat`.
 */
export const CommanderDamage: Story = {
  args: seat({ commander_damage_taken: { "1": 15 } }),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("player-0");
    expect(canvasElement.querySelector('[data-testid="cmddmg-0"]')).toBeNull();
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
 * This column is the viewer's, and nobody else's.
 *
 * It used to draw for opponents too, at two-thirds the size, with a summary
 * line where the viewer got nothing -- so a pod was three control panels for
 * controls nobody could press. An opponent is an `OpponentSeat` now, which
 * answers what have they got on the battlefield instead of offering a commander
 * you cannot cast. The spine went with them.
 */
export const NoSpineAnywhere: Story = {
  args: seat(),
  play: async ({ canvasElement }) => {
    if (canvasElement.querySelector(".orb__spine")) {
      throw new Error("the summary line belongs to OpponentSeat now");
    }
  },
};

/**
 * THE LIFE TOTAL STAYS READABLE AFTER IT CHANGES.
 *
 * The numeral flashes green or red on a life change and then goes back to its
 * resting colour -- and Framer writes that resting colour back as an INLINE
 * style, which beats every rule in the stylesheet. The component once named
 * `--dial-ink` for it, which was right on the old brass seal -- and the dial is
 * a gold ring around a hole punched out of `--void-1` now, so one point of
 * damage stamped near-black ink onto a dark purple well and the life total
 * became unreadable. Only after the first hit.
 *
 * `--dial-n` is the indirection that fixes it: the stylesheet owns the resting
 * ink and the component says "put it back" without knowing what the disc looks
 * like. This is the story that would notice it being named directly
 * again -- so it asserts CONTRAST rather than a colour, because what actually
 * broke was legibility and a token name is not the property.
 */
function reading(el: HTMLElement): number {
  const [r, g, b] = (getComputedStyle(el).color.match(/[\d.]+/g) ?? ["0", "0", "0"]).map(
    Number,
  );
  // Rec. 601 luma is plenty for "is this ink or is it paper".
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
}

/** Renders the orb, then takes a life off it once -- as a hit would. */
function TakesAHit(props: ReturnType<typeof seat>) {
  const [life, setLife] = useState(props.player.life);
  useEffect(() => {
    const id = setTimeout(() => setLife((n) => n - 7), 30);
    return () => clearTimeout(id);
  }, []);
  return <PlayerOrb {...props} player={{ ...props.player, life }} />;
}

export const HandheldLifeStaysReadableAfterAHit: Story = {
  args: seat(),
  globals: { handheld: "on" },
  tags: ["handheld"],
  parameters: { automtg: { mount: "matSide", motion: "real" } },
  render: (args) => <TakesAHit {...(args as ReturnType<typeof seat>)} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const numeral = await canvas.findByTestId("life-0");
    const before = reading(numeral);
    expect(before, "the numeral starts light on this dial").toBeGreaterThan(0.5);

    // The hit lands, the flash plays, and the numeral comes back to rest.
    await waitFor(() => expect(numeral.textContent).toBe("33"));
    await waitFor(
      () => {
        expect(numeral.style.color, "the animation rests inline").not.toBe("");
      },
      { timeout: 2000 },
    );
    await waitFor(
      () => {
        expect(
          reading(numeral),
          `the life total rested at ${getComputedStyle(numeral).color} on a dark dial`,
        ).toBeGreaterThan(0.5);
      },
      { timeout: 2000 },
    );
  },
};
