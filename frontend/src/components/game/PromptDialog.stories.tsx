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
import { expect, fn, userEvent, waitFor, within } from "storybook/test";
import { noteInput, resetInputMode } from "../../input/inputMode";
import { expectHandheldFloors, expectUniqueActionIds, settled } from "../../testing/asserts";
import { action, gameView, pending } from "../../testing/fixtures";
import * as scenarios from "../../testing/scenarios";
import { PromptDialog } from "./PromptDialog";

const meta = {
  title: "Game/PromptDialog",
  component: PromptDialog,
  parameters: { automtg: { mount: "screen" } },
  args: { onAct: fn(), onChoose: fn(), disabled: false },
} satisfies Meta<typeof PromptDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Open the dialog for a scenario, and check the click reaches `onAct`. */
function submits(kind: string, label: string, id: string) {
  return async ({
    canvasElement,
    args,
  }: {
    canvasElement: HTMLElement;
    args: { onAct: unknown };
  }) => {
    const canvas = within(canvasElement);
    const dialog = await canvas.findByTestId("prompt-dialog");
    expect(dialog.dataset.decisionKind).toBe(kind);
    expectUniqueActionIds(canvasElement);
    await userEvent.click(await canvas.findByText(label));
    expect(args.onAct).toHaveBeenCalledWith(id);
  };
}

/*
 * THE MULLIGAN IS NOT ONE OF THESE ANY MORE.
 *
 * It was this file's first story and its simplest -- two options, one press --
 * and `OpeningHand` owns it now, so it is `OpeningHand.stories.tsx`'s. What
 * stands in its place is the smallest decision this dialog still draws: a "may"
 * with a yes and a no.
 *
 * `PromptDialogStandsDown` further down is the half that still belongs here,
 * and it is the one worth keeping: it asserts this dialog does NOT open for a
 * decision another surface owns.
 */
export const Simplest: Story = {
  args: { state: scenarios.mayAbility().state, actions: scenarios.mayAbility().actions },
  play: submits("may", "Yes", "a0-choose"),
};

/**
 * An option, hovered.
 *
 * The options lift `y: -4` and scale 1.03, and they live in a scroll container.
 * With only 4px of padding the lifted top edge -- and the focus ring outside it,
 * which is what a keyboard user is following -- clipped against the container.
 * Nothing about the button says so; it is the parent's `overflow-y` that cuts it.
 */
export const OptionOnHover: Story = {
  args: { state: scenarios.mayAbility().state, actions: scenarios.mayAbility().actions },
  parameters: { automtg: { mount: "screen", motion: "real" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("prompt-dialog");
    const option = canvasElement.querySelector(".opt") as HTMLElement;
    const list = canvasElement.querySelector(".prompt__options") as HTMLElement;

    await userEvent.hover(option);
    await settled(option);

    // Measured after the lift settles -- reading mid-spring measures a button
    // that has not moved yet, which passes against the defect.
    const lifted = option.getBoundingClientRect();
    const scroller = list.getBoundingClientRect();
    expect(
      Math.round(lifted.top),
      "the lifted option clips against the top of its scroll container",
    ).toBeGreaterThanOrEqual(Math.round(scroller.top));
  },
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

/** "Up to two target artifacts and/or enchantments": cards to toggle, then Confirm. */
export const ChooseSeveralTargets: Story = {
  args: {
    state: scenarios.chooseSeveralTargets().state,
    actions: scenarios.chooseSeveralTargets().actions,
  },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const grid = await canvas.findByTestId("pick-several");
    const toggles = within(grid).getAllByRole("button");
    await userEvent.click(toggles[0]);
    await userEvent.click(toggles[3]);
    await userEvent.click(canvas.getByTestId("pick-confirm"));
    expect(args.onChoose).toHaveBeenCalledTimes(1);
  },
};

/**
 * A pick steps the ring on: choosing several is A, A, then Confirm.
 *
 * `.click()` is the ring's `A` (`useCursorNav`), a click with no pointer
 * behind it. The first pick moves to the next card, the one that fills the
 * set moves to Confirm, and an un-pick stays where it is.
 */
export const ChooseSeveralStepsTheRing: Story = {
  args: {
    state: scenarios.chooseSeveralTargets().state,
    actions: scenarios.chooseSeveralTargets().actions,
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const grid = await canvas.findByTestId("pick-several");
    const toggles = within(grid).getAllByRole("button");
    const ringOn = () => canvasElement.querySelector<HTMLElement>("[data-cursor]");

    toggles[0].click();
    await waitFor(() => expect(ringOn()).toBe(toggles[1]));

    toggles[0].click();
    await waitFor(() => expect(toggles[0].getAttribute("aria-pressed")).toBe("false"));
    expect(ringOn(), "an un-pick does not move the ring").toBe(toggles[1]);

    toggles[1].click();
    await waitFor(() => expect(ringOn()).toBe(toggles[2]));
    toggles[2].click();
    await waitFor(() => expect(ringOn()?.getAttribute("data-testid")).toBe("pick-confirm"));
  },
};

export const ChooseTarget: Story = {
  args: { state: scenarios.chooseTarget().state, actions: scenarios.chooseTarget().actions },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("prompt-dialog");
    // An option that names a permanent draws as a real card, not a bare label.
    expect(canvasElement.querySelector('[data-card-name="Serra Angel"]')).not.toBeNull();
    // Clicked by id: the name is on the card face, and the face is not the
    // only text in the dialog, so the text is not a unique handle.
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
/* A decision too long to draw as buttons                              */
/* ------------------------------------------------------------------ */

/**
 * Herald's Horn: choose a creature type, out of every type in the pool.
 *
 * The wall this replaced was 199 buttons here and up to 400 in a full pool --
 * unreadable with a mouse and *unreachable* with a pad past the eighth row,
 * because `candidatesIn` drops stops an ancestor has clipped and the ring
 * focuses with `preventScroll`.
 *
 * One action id in the document, not 199: the rows select, the Choose button
 * acts. `expectUniqueActionIds` would pass either way -- it is the count that
 * says which surface this is.
 */
export const ChooseType: Story = {
  args: { state: scenarios.chooseType().state, actions: scenarios.chooseType().actions },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const dialog = await canvas.findByTestId("prompt-dialog");
    expect(dialog.dataset.decisionKind).toBe("choose_mode");
    expectUniqueActionIds(canvasElement);
    expect(canvasElement.querySelectorAll("[data-action-id]").length).toBe(1);

    await userEvent.type(canvas.getByTestId("combo-filter"), "vam");
    const rows = canvas.getAllByRole("option");
    expect(rows.map((row) => row.textContent)).toEqual(["Vampire"]);

    // Enter commits the highlighted row, which is what the button beside the
    // list is bound to -- typing and pressing return never touches the mouse.
    await userEvent.keyboard("{Enter}");
    expect(args.onAct).toHaveBeenCalledWith(
      scenarios.chooseType().actions.find((a) => a.label === "Vampire")?.id,
    );
  },
};

/**
 * A query that matches nothing.
 *
 * The one prompt story that deliberately does not submit, in a file whose whole
 * rule is that each one does -- the point here is that Choose goes dead rather
 * than committing something arbitrary, and that there is a way back.
 */
export const ChooseTypeEmpty: Story = {
  args: { state: scenarios.chooseType().state, actions: scenarios.chooseType().actions },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("prompt-dialog");
    await userEvent.type(canvas.getByTestId("combo-filter"), "zzzz");

    expect(canvas.queryAllByRole("option")).toEqual([]);
    expect(canvas.getByTestId("combo-empty")).toBeTruthy();
    expect((canvas.getByTestId("combo-go") as HTMLButtonElement).disabled).toBe(true);
    expect(canvasElement.querySelectorAll("[data-action-id]").length).toBe(0);

    await userEvent.click(canvas.getByTestId("combo-clear"));
    expect(canvas.getAllByRole("option").length).toBeGreaterThan(0);
    expect(args.onAct).not.toHaveBeenCalled();
  },
};

/**
 * The same prompt, held on a controller.
 *
 * No autofocus: a focused field deadens the arrow keys that stand in for the
 * d-pad (`pad.ts:isTyping`), so taking the caret would break the only
 * navigation a pad player has. The ring still resolves onto the field, because
 * it is the dialog's first stop.
 *
 * `beforeEach` as well as the global: the decorator stamps `data-input` on
 * `<html>`, which is what the CSS reads, but `getInputMode()` is module state
 * and nothing else writes it -- without this the story would assert nothing.
 */
export const ChooseTypeOnPad: Story = {
  args: { state: scenarios.chooseType().state, actions: scenarios.chooseType().actions },
  globals: { input: "pad" },
  /*
   * Real motion, and measured after it settles.
   *
   * The dialog opens at `scale: 0.96`, and every box inside a transformed
   * ancestor reports scaled -- so a story that measures the fold, or the touch
   * floor, against an unsettled dialog is measuring a 4% smaller screen than
   * the player ever sees. `OptionOnHover` opted into real motion for the same
   * reason, one lift lower down.
   */
  parameters: { automtg: { mount: "screen", motion: "real" } },
  beforeEach: () => {
    noteInput("pad");
    return resetInputMode;
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const dialog = await canvas.findByTestId("prompt-dialog");
    await settled(dialog);
    const field = canvas.getByTestId("combo-filter");
    expect(document.activeElement).not.toBe(field);

    /*
     * THE ROW BELOW THE FOLD IS STILL A STOP.
     *
     * `.combo__list` is sized at eight and a half rows precisely so the next one
     * is half visible: fully clipped, it would not be a candidate, and a down
     * press on the last visible row would report a wall with two hundred
     * options still beneath it.
     */
    const list = canvasElement.querySelector(".combo__list") as HTMLElement;
    const rows = canvas.getAllByRole("option");
    const box = list.getBoundingClientRect();
    const peeking = rows.filter((row) => {
      const r = row.getBoundingClientRect();
      return r.top < box.bottom && r.bottom > box.bottom;
    });
    expect(peeking.length, "no row straddles the fold, so the ring hits a wall").toBe(1);
  },
};

/** And on a handheld, where the rows have to clear the touch floor. */
export const ChooseTypeHandheld: Story = {
  args: { state: scenarios.chooseType().state, actions: scenarios.chooseType().actions },
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  parameters: { automtg: { mount: "screen", motion: "real" } },
  beforeEach: () => {
    noteInput("pad");
    return resetInputMode;
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const dialog = await canvas.findByTestId("prompt-dialog");
    await settled(dialog);
    expectHandheldFloors(canvasElement);
  },
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
    state: scenarios.mayAbility().state,
    actions: scenarios.mayAbility().actions,
    disabled: true,
  },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("prompt-dialog");
    await userEvent.click(await canvas.findByText("Yes"));
    expect(args.onAct).not.toHaveBeenCalled();
  },
};

/**
 * And it stays shut for the two kinds `OpeningHand` owns.
 *
 * The mulligan is a kind in the denylist; its bottoming half is not, because it
 * arrives as a `choose_objects` and every other `choose_objects` is still this
 * dialog's. So the two halves are excluded by two different mechanisms, and
 * both are worth one assertion.
 */
export const StandsDownForTheOpeningHand: Story = {
  args: { state: scenarios.mulligan().state, actions: scenarios.mulligan().actions },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(canvas.queryByTestId("prompt-dialog")).toBeNull();
  },
};

export const StandsDownForTheBottomingHalf: Story = {
  args: {
    state: scenarios.mulliganBottom().state,
    actions: scenarios.mulliganBottom().actions,
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(canvas.queryByTestId("prompt-dialog")).toBeNull();
  },
};
