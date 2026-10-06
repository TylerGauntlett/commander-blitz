/**
 * The effects layer: damage numerals, spotlights, banners and flashes.
 *
 * Beats are handed in directly here rather than played through the narration
 * queue, which keeps each effect a thing you can look at instead of a moment you
 * have to catch. The layer anchors its effects to real elements by `data-oid`
 * and `data-player`, so like `CombatArrows` it needs a board underneath it and
 * cannot say anything at all in jsdom.
 *
 * Note these stories run at `speed: "cinematic"` rather than the harness default
 * of `instant`: `narration.ts` short-circuits on instant and drops beats rather
 * than holding them, so an instant FX story would have nothing to draw.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { useLayoutEffect, useRef } from "react";
import { expect, waitFor, within } from "storybook/test";
import type { ExitFx } from "../../logic/beats/types";
import { reset as forgetRects, remember } from "../../logic/cardRects";
import { CARD_SCALE, opponentCardScale } from "../../logic/cardSize";
import { seatOrder } from "../../logic/zoneGrouping";
import type { LiveBeat } from "../../state/narration";
import { settled } from "../../testing/asserts";
import * as scenarios from "../../testing/scenarios";
import { FxLayer } from "./FxLayer";
import { PlayerMat } from "./PlayerMat";

const state = scenarios.combatDeclareAttackers().state;

/**
 * A board to anchor against, plus the overlay on top of it.
 *
 * `seed` stands in for what `Card` does on unmount. A ghost is drawn from a
 * card's *last known* box (`logic/cardRects.ts`), so a story about the ghost
 * needs those boxes on record -- and measuring the real cards on this board is
 * both closer to the truth than a literal and what proves the layer converts
 * viewport coordinates to board-relative ones correctly.
 *
 * A layout effect in the parent runs after its children have mounted and before
 * any passive effect, so the registry is populated before `FxLayer` reads it.
 */
function Stage({ beat, seed = [] }: { beat: LiveBeat | null; seed?: number[] }) {
  const boardRef = useRef<HTMLDivElement>(null);
  const opponents = seatOrder(state).filter((pid) => pid !== state.seat);

  useLayoutEffect(() => {
    forgetRects();
    for (const oid of seed) {
      const el = document.querySelector(`[data-oid="${oid}"]`);
      if (el) remember(oid, el.getBoundingClientRect());
    }
  }, [seed]);

  return (
    <div ref={boardRef} className="play" style={{ position: "relative", height: "90vh" }}>
      <div className="play__opponents">
        {opponents.map((pid) => (
          <PlayerMat
            key={pid}
            state={state}
            player={state.players[pid]}
            compact
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
      <FxLayer beat={beat} speed="cinematic" boardRef={boardRef} state={state} />
    </div>
  );
}

/** A beat, with the uid the queue would have stamped on it. */
function beat(overrides: Partial<LiveBeat> = {}): LiveBeat {
  return { id: "b1", uid: 1, hold: 600, text: null, ...overrides } as LiveBeat;
}

/** One departure, shaped as `beatsFor` would have shaped it. */
function exit(oid: number, overrides: Partial<ExitFx> = {}): ExitFx {
  return {
    oid,
    cardId: "grizzly_bears",
    name: "Grizzly Bears",
    owner: 0,
    to: "graveyard",
    cause: "destroyed",
    caption: "Destroyed by Swords to Plowshares",
    ...overrides,
  };
}

const meta = {
  title: "Game/FxLayer",
  component: FxLayer,
  parameters: { automtg: { mount: "tableBody" } },
  args: { beat: null, speed: "cinematic", state, boardRef: { current: null } },
} satisfies Meta<typeof FxLayer>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Nothing playing: the layer is present and draws nothing. */
export const Idle: Story = {
  render: () => <Stage beat={null} />,
};

/** Damage, floating up off the player who took it. */
export const DamageNumeral: Story = {
  render: () => (
    <Stage
      beat={beat({
        float: { anchor: { kind: "player", pid: 1 }, value: "-7", tone: "damage" },
      })}
    />
  ),
  play: async ({ canvasElement }) => {
    await waitFor(() => {
      const canvas = within(canvasElement);
      expect(canvas.getByText("-7")).toBeTruthy();
    });
  },
};

/** Life gained, off the viewer. */
export const LifeGain: Story = {
  render: () => (
    <Stage
      beat={beat({ float: { anchor: { kind: "player", pid: 0 }, value: "+5", tone: "gain" } })}
    />
  ),
};

/** A spell thrown up in the middle of the screen as it is cast. */
export const Spotlight: Story = {
  render: () => (
    <Stage
      beat={beat({
        hold: 1200,
        spotlight: {
          cardId: "thragtusk",
          name: "Thragtusk",
          controller: 1,
          kind: "spell",
        },
      })}
    />
  ),
  play: async ({ canvasElement }) => {
    await waitFor(() => {
      const canvas = within(canvasElement);
      expect(canvas.getAllByText("Thragtusk").length).toBeGreaterThan(0);
    });
  },
};

/**
 * A trigger, which reads differently from a spell.
 *
 * A trigger is something happening *to* you and is not a card leaving anyone's
 * hand, so `kind` distinguishes them rather than the two sharing a treatment.
 */
export const TriggerSpotlight: Story = {
  render: () => (
    <Stage
      beat={beat({
        hold: 1200,
        spotlight: {
          cardId: "rhystic_study",
          name: "Rhystic Study",
          controller: 0,
          kind: "trigger",
        },
      })}
    />
  ),
};

/**
 * A permanent leaving the battlefield.
 *
 * This replaced a `dies` flash that drew nothing, ever: the flash anchored to
 * `[data-oid]`, and a card being destroyed is by definition one the board has
 * stopped rendering, so the lookup returned null every single time. The ghost is
 * drawn from the card's last known box instead.
 */
export const CardExit: Story = {
  render: () => (
    <Stage
      seed={[303]}
      beat={beat({ hold: 900, sound: undefined, exits: [exit(303, { name: "Thragtusk" })] })}
    />
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await waitFor(() => expect(canvas.getByTestId("card-ghost")).toBeTruthy());
    // The whole point: the player is told *why*, not merely that it happened.
    expect(canvas.getByText("Destroyed by Swords to Plowshares")).toBeTruthy();
  },
};

/**
 * The ghost really does travel towards the pile it lands in.
 *
 * Real geometry, which is why this is a story and not a unit test -- jsdom
 * reports every box as 0x0, so the registry's own guard would drop the seed and
 * there would be nothing to measure.
 */
export const FliesToTheGraveyard: Story = {
  // The flight *is* the transform, and `reducedMotion` removes exactly that --
  // under the harness default this story would measure a ghost already parked
  // on the pile and assert nothing at all.
  parameters: { automtg: { mount: "tableBody", motion: "real" } },
  render: () => (
    <Stage
      seed={[303]}
      beat={beat({ hold: 1400, exits: [exit(303, { name: "Thragtusk" })] })}
    />
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const ghost = await waitFor(() => canvas.getByTestId("card-ghost"));
    const pile = canvasElement.querySelector('[data-testid="pile-0-graveyard"]') as HTMLElement;
    const target = pile.getBoundingClientRect();
    const distance = (box: DOMRect) =>
      Math.hypot(
        box.left + box.width / 2 - (target.left + target.width / 2),
        box.top + box.height / 2 - (target.top + target.height / 2),
      );

    const started = distance(ghost.getBoundingClientRect());
    await settled(ghost);
    expect(distance(ghost.getBoundingClientRect())).toBeLessThan(started);
  },
};

/**
 * Exile, which reads differently on purpose.
 *
 * Whether a creature can be recurred is the question a player is asking as it
 * leaves, and having to read the caption to find out is too slow.
 */
export const ExitToExile: Story = {
  render: () => (
    <Stage
      seed={[303]}
      beat={beat({
        hold: 900,
        exits: [
          exit(303, { name: "Thragtusk", to: "exile", cause: "exiled", caption: "Exiled" }),
        ],
      })}
    />
  ),
  play: async ({ canvasElement }) => {
    const ghost = await waitFor(() => within(canvasElement).getByTestId("card-ghost"));
    expect(ghost.className).toContain("fx-ghost--exile");
  },
};

/**
 * A board wipe: one beat, several ghosts, staggered.
 *
 * Five sequential beats at a readable single-death pace would hold the board
 * for six seconds. The queue moves on after one short hold and the FX layer
 * keeps flying, which is what this layer's overlapping-effects design is for.
 */
export const BoardWipe: Story = {
  render: () => (
    <Stage
      seed={[301, 302, 303, 304, 305]}
      beat={beat({
        hold: 1600,
        text: "5 permanents leave the battlefield",
        exits: [
          exit(301, { name: "Llanowar Elves", caption: "Destroyed by Wrath of God" }),
          exit(302, { name: "Serra Angel", caption: "Destroyed by Wrath of God" }),
          exit(303, { name: "Thragtusk", caption: "Destroyed by Wrath of God" }),
          exit(304, { name: "Forest", caption: "Destroyed by Wrath of God" }),
          exit(305, { name: "Plains", caption: "Destroyed by Wrath of God" }),
        ],
      })}
    />
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await waitFor(() => expect(canvas.getAllByTestId("card-ghost")).toHaveLength(5));
  },
};

/**
 * A card whose position was never recorded draws nothing.
 *
 * Deliberate, and the alternative is worse: with no last known box the only
 * options are to invent one or to drop the ghost, and inventing one puts an
 * opponent's creature in the middle of the viewer's own board on its way out.
 */
export const UnknownPositionIsSkipped: Story = {
  render: () => <Stage seed={[]} beat={beat({ hold: 900, exits: [exit(303)] })} />,
  play: async ({ canvasElement }) => {
    // Give the effect a frame to have done nothing.
    await new Promise((resolve) => setTimeout(resolve, 120));
    expect(within(canvasElement).queryByTestId("card-ghost")).toBeNull();
  },
};

/** A full-width sweep: turn changes and eliminations. */
export const Banner: Story = {
  render: () => (
    <Stage
      beat={beat({ hold: 1400, banner: { text: "AI 1 has been eliminated", tone: "danger" } })}
    />
  ),
  play: async ({ canvasElement }) => {
    await waitFor(() => {
      const canvas = within(canvasElement);
      expect(canvas.getByText(/eliminated/)).toBeTruthy();
    });
  },
};
