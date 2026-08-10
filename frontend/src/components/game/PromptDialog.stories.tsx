/**
 * Every decision that is not priority and not combat.
 *
 * The dialog is the surface of last resort: `full-game.spec.ts` drives a whole
 * game by clicking legal actions, and *if any decision kind has no surface the
 * loop runs out of buttons and the spec fails*. So there is one story per kind,
 * and each one submits, which is the same coverage question asked cheaply.
 *
 * `isModalDecision` is the other half of the contract -- whichever surface owns
 * a decision renders its ids and every other one stands down.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { expectUniqueActionIds } from "../../testing/asserts";
import { action, gameView, pending } from "../../testing/fixtures";
import * as scenarios from "../../testing/scenarios";
import { PromptDialog } from "./PromptDialog";

const meta = {
  title: "Game/PromptDialog",
  component: PromptDialog,
  parameters: { automtg: { mount: "screen" } },
  args: { onAct: fn(), disabled: false },
} satisfies Meta<typeof PromptDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Open the dialog for a scenario, and check the click reaches `onAct`. */
function submits(kind: string, label: string, id: string) {
  return async ({
    canvasElement,
    args,
  }: { canvasElement: HTMLElement; args: { onAct: unknown } }) => {
    const canvas = within(canvasElement);
    const dialog = await canvas.findByTestId("prompt-dialog");
    expect(dialog.dataset.decisionKind).toBe(kind);
    expectUniqueActionIds(canvasElement);
    await userEvent.click(await canvas.findByText(label));
    expect(args.onAct).toHaveBeenCalledWith(id);
  };
}

export const Mulligan: Story = {
  args: { state: scenarios.mulligan().state, actions: scenarios.mulligan().actions },
  play: submits("mulligan", "Keep", "a0-keep"),
};

export const DiscardToHandSize: Story = {
  args: {
    state: scenarios.discardToHandSize().state,
    actions: scenarios.discardToHandSize().actions,
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const dialog = await canvas.findByTestId("prompt-dialog");
    expect(dialog.dataset.decisionKind).toBe("discard_to_hand_size");
    // Two of nine: the range has to be stated, or "choose" is ambiguous.
    expect(dialog.textContent).toMatch(/2/);
    expectUniqueActionIds(canvasElement);
  },
};

export const ChooseTarget: Story = {
  args: { state: scenarios.chooseTarget().state, actions: scenarios.chooseTarget().actions },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("prompt-dialog");
    // An option that names a permanent draws as a real card, not a bare label.
    expect(canvasElement.querySelector('[data-card-name="Serra Angel"]')).not.toBeNull();
    // Clicked by id: the option renders the name twice, once on the card face
    // and once as the caption under it, so the text is not a unique handle.
    await userEvent.click(
      canvasElement.querySelector('[data-action-id="a1-choose"]') as HTMLElement,
    );
    expect(args.onAct).toHaveBeenCalledWith("a1-choose");
  },
};

export const ChooseMode: Story = {
  args: { state: scenarios.chooseMode().state, actions: scenarios.chooseMode().actions },
  play: submits("choose_mode", "Return target creature to its owner's hand", "a1-choose"),
};

/**
 * Pointing at a player.
 *
 * The label is restated with the resolved name in brackets -- "AI 2 (AI 2)" here,
 * which reads oddly only because the fixture's label is already the name. In a
 * real game the label is the effect ("Target opponent discards a card") and the
 * bracket is what says who.
 */
export const ChoosePlayer: Story = {
  args: { state: scenarios.choosePlayer().state, actions: scenarios.choosePlayer().actions },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const dialog = await canvas.findByTestId("prompt-dialog");
    expect(dialog.dataset.decisionKind).toBe("choose_player");
    expectUniqueActionIds(canvasElement);
    await userEvent.click(
      canvasElement.querySelector('[data-action-id="a2-choose"]') as HTMLElement,
    );
    expect(args.onAct).toHaveBeenCalledWith("a2-choose");
  },
};

export const MayAbility: Story = {
  args: { state: scenarios.mayAbility().state, actions: scenarios.mayAbility().actions },
  play: submits("may", "Yes", "a0-choose"),
};

/**
 * Searching a library.
 *
 * The cards are in a zone the player view reports as a count, so `findCard`
 * cannot resolve them -- the faces come from `option.card`, which exists for
 * exactly this. Without it the prompt is a row of names.
 */
export const SearchLibrary: Story = {
  args: { state: scenarios.searchLibrary().state, actions: scenarios.searchLibrary().actions },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("prompt-dialog");
    expect(
      canvasElement.querySelectorAll("[data-card-name]").length,
      "library cards rendered as labels rather than faces",
    ).toBeGreaterThan(0);
  },
};

export const CommanderZoneChange: Story = {
  args: {
    state: gameView({
      pending: pending({
        kind: "commander_zone_change",
        prompt: "Put Aesi into the command zone instead?",
      }),
    }),
    actions: [
      action({ id: "a0-choose", kind: "choose", label: "Command zone" }),
      action({ id: "a1-choose", kind: "choose", label: "Graveyard" }),
    ],
  },
  play: submits("commander_zone_change", "Command zone", "a0-choose"),
};

/* ------------------------------------------------------------------ */
/* When the dialog must not open                                       */
/* ------------------------------------------------------------------ */

/** Priority and combat have their own surfaces, so the dialog stays shut. */
export const ShutForPriority: Story = {
  args: { state: gameView(), actions: [action()] },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(canvas.queryByTestId("prompt-dialog")).toBeNull();
  },
};

export const ShutForCombat: Story = {
  args: {
    state: gameView({ pending: pending({ kind: "declare_attackers" }) }),
    actions: [action()],
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(canvas.queryByTestId("prompt-dialog")).toBeNull();
  },
};

/** Somebody else's decision: nothing to show, and nothing to click. */
export const NotMyDecision: Story = {
  args: {
    state: gameView({
      pending: pending({ kind: "choose_objects", player: 1, prompt: "AI 1 is choosing" }),
    }),
    actions: [action()],
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(canvas.queryByTestId("prompt-dialog")).toBeNull();
  },
};

/** Input gated while a request is in flight. */
export const Disabled: Story = {
  args: {
    state: scenarios.mulligan().state,
    actions: scenarios.mulligan().actions,
    disabled: true,
  },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("prompt-dialog");
    await userEvent.click(await canvas.findByText("Keep"));
    expect(args.onAct).not.toHaveBeenCalled();
  },
};
