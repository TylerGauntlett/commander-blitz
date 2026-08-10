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
import { useRef } from "react";
import { expect, waitFor, within } from "storybook/test";
import { CARD_SCALE, opponentCardScale } from "../../logic/cardSize";
import { seatOrder } from "../../logic/zoneGrouping";
import type { LiveBeat } from "../../state/narration";
import * as scenarios from "../../testing/scenarios";
import { FxLayer } from "./FxLayer";
import { PlayerMat } from "./PlayerMat";

const state = scenarios.combatDeclareAttackers().state;

/** A board to anchor against, plus the overlay on top of it. */
function Stage({ beat }: { beat: LiveBeat | null }) {
  const boardRef = useRef<HTMLDivElement>(null);
  const opponents = seatOrder(state).filter((pid) => pid !== state.seat);

  return (
    <div ref={boardRef} className="play" style={{ position: "relative", height: "90vh" }}>
      <div className="play__opponents">
        {opponents.map((pid) => (
          <PlayerMat
            key={pid}
            state={state}
            player={state.players[pid]}
            names={state.players.map((p) => p.name)}
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
        names={state.players.map((p) => p.name)}
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

/** A permanent dying: a flash on it, and a line in the log. */
export const Death: Story = {
  render: () => (
    <Stage
      beat={beat({
        text: "Grizzly Bears dies",
        flash: { anchor: { kind: "object", oid: 350 }, tone: "loss" },
      })}
    />
  ),
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
