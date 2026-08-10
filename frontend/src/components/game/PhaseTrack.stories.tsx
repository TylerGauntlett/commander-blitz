/**
 * Where we are in the turn.
 *
 * The engine walks thirteen steps and auto-passes anything with one legal
 * action, so the track is often the only evidence a step happened at all. Only
 * the live phase opens into its steps; the closed ones stay in the DOM with
 * `display: none`, which is why every label is still findable here.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";
import { gameView } from "../../testing/fixtures";
import { PhaseTrack } from "./PhaseTrack";

const meta = {
  title: "Game/PhaseTrack",
  component: PhaseTrack,
  parameters: { automtg: { mount: "trackRow" } },
} satisfies Meta<typeof PhaseTrack>;

export default meta;
type Story = StoryObj<typeof meta>;

/** One story per phase, since only the live phase opens. */
const at = (step: string, phase: string, extra = {}) => ({
  state: gameView({ step, phase, ...extra }),
});

export const Upkeep: Story = { args: at("UPKEEP", "beginning") };
export const Draw: Story = { args: at("DRAW", "beginning") };
export const PrecombatMain: Story = { args: at("PRECOMBAT_MAIN", "precombat_main") };
export const DeclareAttackers: Story = { args: at("DECLARE_ATTACKERS", "combat") };
export const DeclareBlockers: Story = { args: at("DECLARE_BLOCKERS", "combat") };
export const CombatDamage: Story = { args: at("COMBAT_DAMAGE", "combat") };
export const PostcombatMain: Story = { args: at("POSTCOMBAT_MAIN", "postcombat_main") };
export const EndStep: Story = { args: at("END_STEP", "ending") };

/** All thirteen labels stay in the document even while their phase is shut. */
export const EveryStepIsPresent: Story = {
  args: at("DECLARE_BLOCKERS", "combat"),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("phase-track");
    const labels = [...canvasElement.querySelectorAll(".track__step-label")];
    expect(labels).toHaveLength(13);
    expect(labels.every((node) => (node.textContent ?? "").length > 0)).toBe(true);
    // Exactly one marker, on exactly one step.
    expect(canvasElement.querySelectorAll(".track__step--now")).toHaveLength(1);
  },
};

/**
 * The counter counts rounds, not player-turns.
 *
 * `state.turn` is the rules counter -- it decides summoning sickness -- and in a
 * pod it climbs four times a lap, so it is not what anybody means by "my second
 * turn". Both are here; only one is big.
 */
export const PodRoundCounter: Story = {
  args: at("PRECOMBAT_MAIN", "precombat_main", { turn: 14, round: 4 }),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const counter = await canvas.findByTestId("turn-counter");
    expect(counter.dataset.round).toBe("4");
    expect(counter.dataset.turn).toBe("14");
    expect(counter.textContent).toContain("T4");
  },
};

/** Somebody else's turn: the chip at the far end says whose. */
export const OpponentsTurn: Story = {
  args: at("UPKEEP", "beginning", { active_player: 1 }),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("AI 1's turn");
  },
};

/**
 * A step the track does not know.
 *
 * It marks everything "future", which looks exactly like a track that never
 * advances -- so the component warns in dev. The assertion here is only on the
 * rendered output, because `import.meta.env.DEV` differs between `storybook dev`
 * and this runner and a story that depended on the warning would disagree with
 * itself.
 */
export const UnknownStep: Story = {
  args: at("SOME_NEW_STEP", "combat"),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("phase-track");
    expect(canvasElement.querySelectorAll(".track__step--now")).toHaveLength(0);
  },
};
