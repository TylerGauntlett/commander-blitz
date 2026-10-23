/**
 * The core journeys, counted in presses.
 *
 * Every other gate in this suite answers "can a controller reach this". These
 * answer "and how long does it take", which is the property a player feels and
 * the one that regresses in silence -- a stop added to a lane, a region entered
 * on the wrong side, a ring left on a card that changed zones, and a two-press
 * decision becomes a nine-press one with nothing failing anywhere.
 *
 * ## Why the hook is mounted by hand
 *
 * `useCursorNav` binds `A` and the four directions, and `Screen` is what mounts
 * it in the app -- so a story that rendered `Table` alone would be pressing
 * buttons nothing was listening for, and every journey would "cost" whatever
 * number the assertion was written with. `Playable` mounts the hook the way the
 * app does, which is the smallest thing that makes a press mean something.
 *
 * ## What is here and what is in e2e
 *
 * These are the journeys made entirely of client-side staging: targeting,
 * blocking, and the two combat shortcuts. They are true the moment the gesture
 * is made, so a fixture is a faithful stand-in for the engine.
 *
 * Playing a card is NOT here. It is a server mutation, the follow-up
 * deliberately waits for the new action list before moving the ring, and
 * `fakeGame` never produces one -- so the honest place for it is
 * `e2e/journeys-handheld.spec.ts`, against a real engine.
 *
 * ## The budgets are ceilings, and they live in the audit
 *
 * `toBeLessThanOrEqual`, always. An exact count fails on an improvement, which
 * is the wrong direction to be strict in. Each number is what the journey
 * measured against the real engine at 1280x800, and it is written down once,
 * in `decisionAudit.ts`, under the name of the story that measures it: the
 * audit is the table of every question the engine asks against the surface
 * that answers it, and the ceiling is the column that makes "one selection
 * model" a number rather than a mood. A story here is held to `ceiling(<its
 * own name>)`, and `tests/decisionAudit.test.ts` fails on a ceiling with no
 * story of that name.
 *
 * ## One journey per decision kind
 *
 * Every kind the engine raises has a journey below, so a surface that moves a
 * question -- a pick that stops landing the ring on its first option, a slab
 * that gains a stop in front of it -- costs a press here before it costs one
 * on a Deck. The pick-one journeys stand for every `choose_objects` purpose
 * the dialog still answers; the audit's rows say which those are.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, waitFor, within } from "storybook/test";
import { useCursorNav } from "../../input/useCursorNav";
import { expectNothingOverflows, expectUniqueActionIds } from "../../testing/asserts";
import { fakeGame, idleMutation } from "../../testing/fakeGame";
import { journey } from "../../testing/journey";
import type { Scenario } from "../../testing/scenarios";
import * as scenarios from "../../testing/scenarios";
import { ceiling } from "./decisionAudit";
import { Table } from "./Table";

type Props = Parameters<typeof Table>[0];

/**
 * The board, with the half of the controller that lives on `Screen`.
 *
 * `useCursorNav` also calls `startPad()`, which is what arms the key latch --
 * so this one line covers the binding and the polling loop together.
 */
function Playable(props: Props) {
  useCursorNav();
  return <Table {...props} />;
}

function board(scenario: Scenario, game = {}): Props {
  return {
    session: { gameId: "story", seat: 0 },
    state: scenario.state,
    game: fakeGame({ state: scenario.state, actions: scenario.actions, ...game }),
    onQuit: fn(),
    onRematch: fn(),
  } as Props;
}

const meta = {
  title: "Game/Journeys",
  component: Table,
  parameters: { commanderblitz: { mount: "screen", zoomLock: false } },
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  render: (args: Props) => <Playable {...args} />,
} satisfies Meta<typeof Table>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Declaring an attack: four presses, and the ranking decides what goes.
 *
 * `L2` puts the ring on the "all" mark (`Table.jumpToCommit` lands there rather
 * than on the slab, because the slab is disabled until something is staged),
 * `A` stages, `right` reaches the slab, `A` declares.
 *
 * What changed is not the count but what the first press does. It used to stage
 * every legal attacker -- so the shortcut for the most consequential decision of
 * the turn was the one you undid card by card. Here Llanowar Elves is a 1/1 into
 * an untapped 2/2 and stays home; Serra Angel flies over it and Thragtusk walks
 * through it.
 */
export const DeclareAnAttack: Story = {
  args: board(scenarios.combatDeclareAttackers()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    const run = journey();

    await run.press("l2");
    await waitFor(() => expect(run.at()).toBe("commit:all"));

    const mark = await canvas.findByTestId("combat-all");
    expect(mark.getAttribute("aria-label")).toBe("All attack (2 of 3)");

    await run.press("a");
    await waitFor(() =>
      expect(canvasElement.querySelector(".commit-note")?.textContent).toBe("2 attacking"),
    );

    // The 1/1 that would have died for nothing is still at home, and is one
    // press away on its own card.
    expect(canvasElement.querySelector('[data-attacker="301"][data-staged]')).toBeNull();

    await run.walk("right", "a");
    expect(run.cost, run.trail.join("\n")).toBeLessThanOrEqual(ceiling("DeclareAnAttack"));
    expectUniqueActionIds(canvasElement);
  },
};

/**
 * ...OR TWO PRESSES OF `X`, FROM WHEREVER YOU ARE STANDING.
 *
 * The four above are the walk: jump to the dock, stage, step right, declare.
 * `X` is the same decision without the walk, because every decision this game
 * asks ends at one control and `X` is the hotkey for it -- `All attack` while
 * nothing is staged, `Attack` once something is.
 *
 * THE FIRST PRESS STAGES AND DOES NOT SUBMIT, which is what makes it safe to
 * put on a hotkey: it is reversible, and by the time the second press commits
 * the hint bar has changed from `All attack` to `Attack` and said so.
 */
export const CommitFromAnywhere: Story = {
  args: board(scenarios.combatDeclareAttackers()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    const run = journey();

    // On the board, nowhere near the rail the dock lives in.
    await waitFor(() => expect(run.region()).toBe("board"));
    await waitFor(() => expect(verbFor(canvasElement, "x")).toBe("All attack"));

    await run.press("x");
    await waitFor(() =>
      expect(canvasElement.querySelector(".commit-note")?.textContent).toBe("2 attacking"),
    );
    // The bar changed with it: the next press is the one that commits.
    await waitFor(() => expect(verbFor(canvasElement, "x")).toBe("Attack"));

    await run.press("x");
    expect(run.cost, run.trail.join("\n")).toBeLessThanOrEqual(ceiling("CommitFromAnywhere"));
    // The ring never left the board to do any of it.
    expect(run.region(), run.trail.join("\n")).toBe("board");
  },
};

/**
 * THE BAR NEVER NAMES A CONTROL THAT WOULD DO NOTHING.
 *
 * `logic/commit.ts` is one rule with two consumers -- `Table.secondary` presses
 * it, `logic/verbs.ts` prints its name -- so they cannot disagree with each
 * other. What they CAN drift from is the panel, whose `disabled` conditions are
 * written in `ActionPanel` and derived separately. A bar advertising `X All
 * defend` over a greyed-out mark is the exact defect `verbs.ts` exists to
 * prevent, arriving through the one seam the shared rule does not cover.
 *
 * So this renders the real panel and checks the agreement, at both decisions.
 * The case that earns it is "All defend": it declines a chump block, so on a
 * board where every block throws a creature away the mark is disabled and `X`
 * has to go quiet rather than reach past it to "No blocks" -- taking the damage
 * is a decision a player makes, not a default.
 *
 * ONE HINT, ADDRESSED. Reading the whole bar and asking whether it contains a
 * word cannot say which button the word belongs to: `A Attack` and `X All
 * attack` are both in there during a declaration. `Glyph` already stamps
 * `data-glyph` on the letter it draws, so no test seam had to be added.
 */
const CONTROL_FOR: Record<string, string> = {
  "All attack": "combat-all",
  "All defend": "combat-all",
  Attack: "combat-confirm",
  Block: "combat-confirm",
  "No attacks": "combat-skip",
  "No blocks": "combat-skip",
};

/** The verb the bar prints under one glyph, or null when it prints none. */
function verbFor(root: HTMLElement, btn: string): string | null {
  return (
    root
      .querySelector(`[data-testid="hint-bar"] .hint:has([data-glyph="${btn}"]) .hint__verb`)
      ?.textContent?.trim() || null
  );
}

/** True when it had something to check, so a story can refuse to pass vacuously. */
function barAgreesWithTheDock(root: HTMLElement): boolean {
  const verb = verbFor(root, "x");
  const named = verb ? CONTROL_FOR[verb] : undefined;
  if (!named) return false;
  const control = root.querySelector<HTMLButtonElement>(`[data-testid="${named}"]`);
  expect(control, `the bar says "X ${verb}" and no ${named} is rendered`).not.toBeNull();
  expect(control?.disabled, `the bar says "X ${verb}" over a disabled ${named}`).toBe(false);
  return true;
}

export const TheBarAgreesWithTheDock: Story = {
  args: board(scenarios.combatDeclareAttackers()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    // Nothing staged, so the bar is offering the mark. A story that checked
    // nothing would pass just as quietly as one that checked and agreed.
    expect(barAgreesWithTheDock(canvasElement), "the bar offered no X verb to check").toBe(
      true,
    );

    // ...and again once something is staged, which is the other half of the
    // rule and a different control. Serra Angel has two legal defenders here,
    // so the ring lands on a stop where `X` means Re-aim -- the contextual verb
    // wins, which is itself the contract, so this half checks the panel from
    // the commit dock's own stop instead.
    await userEvent.click(
      canvasElement.querySelector('.play__mine [data-oid="302"]') as HTMLElement,
    );
    await waitFor(() =>
      expect(canvasElement.querySelector(".commit-note")?.textContent).toMatch(/^1 attacking/),
    );
    expect(canvas.getByTestId("combat-confirm")).toBeEnabled();
    barAgreesWithTheDock(canvasElement);
  },
};

export const TheBarAgreesWhileBlocking: Story = {
  args: board(scenarios.combatDeclareBlockers()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    /*
     * `combatDeclareBlockers` has a Serra Angel that blocks a 2/2 for free, so
     * the mark IS enabled here and the bar must say so. The disabled case is
     * the one `tests/commit.test.ts` pins directly, because posing it needs a
     * board where every block is a chump.
     */
    expect(barAgreesWithTheDock(canvasElement), "the bar offered no X verb to check").toBe(
      true,
    );
  },
};

/**
 * ...and the second press on the same mark is the alpha strike.
 *
 * Racing is a real decision and no arithmetic here should be allowed to make it
 * two dozen presses. The escalation lives on the same control rather than
 * beside it because a second mark in a three-button dock at the 44px hit floor
 * is a row that no longer fits.
 */
export const SendEverythingAnyway: Story = {
  args: board(scenarios.combatDeclareAttackers()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    const run = journey();

    await run.walk("l2", "a", "a");
    await waitFor(() =>
      expect(canvasElement.querySelector(".commit-note")?.textContent).toBe("3 attacking"),
    );
    expect(run.cost, run.trail.join("\n")).toBeLessThanOrEqual(ceiling("SendEverythingAnyway"));
  },
};

/**
 * THE BLOCK DECISION IS NOT ON THE BOARD AT 1280x800, AND THE RING USED TO BE
 * SENT THERE ANYWAY.
 *
 * A block is your creature and then the attacker it stops. An opponent's lanes
 * are clipped to zero height at this size, so `stops.ts:onScreen` refuses to
 * land the ring on an attacker -- correctly. The board therefore held exactly
 * half a decision: pressing your own creature answered nothing, and every
 * direction out of it was a wall or a seat, while the panel had carried the
 * whole pairing as rows the entire time.
 */
export const TheBlockDecisionIsReachable: Story = {
  args: board(scenarios.combatDeclareBlockers()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");

    // The attackers are drawn, and none of them is somewhere the ring can go.
    const attacking = [...canvasElement.querySelectorAll(".play__opponents [data-oid]")];
    expect(attacking.length, "the opponent's board is still in the document").toBeGreaterThan(
      0,
    );

    await waitFor(() =>
      expect(
        document.documentElement.getAttribute("data-group"),
        "the ring must not be parked on a board that cannot answer",
      ).toBe("acts"),
    );

    const run = journey();
    expect(run.at()?.startsWith("act:") || run.at()?.startsWith("commit"), run.trail[0]).toBe(
      true,
    );
    expectNothingOverflows(canvasElement);
  },
};

/**
 * Picking a blocker leaves the ring on the block, not on the blocker.
 *
 * The click stands in for the first of the two presses -- a pointer and the
 * ring route through the same `onBoardCard`, which is the invariant
 * `useCursorNav` exists to keep -- and what is asserted is that the SECOND
 * press finishes the block without a walk in between.
 *
 * Selecting your creature sends the ring to the best block that
 * creature can make -- `card:<attacker>` if the layout draws it, and the panel
 * row for the SAME pairing if it does not. At 1280x800 it is always the row,
 * which is why the fallback is per-attacker rather than a block of rows at the
 * end: falling through to the next row down would make the block the ranking
 * had just rejected.
 */
export const AimABlocker: Story = {
  args: board(scenarios.combatDeclareBlockers()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    const run = journey();

    // Serra Angel, 4/4: the one blocker on this board with a free block to make.
    const angel = canvasElement.querySelector<HTMLElement>(
      '.play__mine [data-oid="403"]',
    ) as HTMLElement;
    await userEvent.click(angel);
    /*
     * The panel row, and not the attacker's card -- at 1280x800 the attacker is
     * in a lane clipped to zero height, so the fallback is what lands. The row
     * is also below the fold of the action list, which is why the follow-up
     * filters by `sendableIn` rather than by what is on screen right now: a
     * jump scrolls its destination into view and a step does not.
     */
    await waitFor(() => expect(run.at()).toMatch(/^act:a-blk-403-/));

    await run.press("a");
    await waitFor(() =>
      expect(canvasElement.querySelector(".commit-note")?.textContent).toMatch(/^1 blocked/),
    );
    expect(run.cost, run.trail.join("\n")).toBeLessThanOrEqual(ceiling("AimABlocker"));
    expectUniqueActionIds(canvasElement);
  },
};

/**
 * Casting a spell that needs a target: two presses, and the second one is on
 * the target.
 *
 * `beginTargeting` lit the board up and moved nothing, so the ring sat on the
 * card in your hand while every legal target was somewhere else -- and on a
 * handheld the ones on an opponent's board are not stops at all. That is why
 * `followUpStops` returns a LIST: the caller takes the first candidate that is
 * actually landable, so the card wins where it is drawn and the panel row for
 * the same action wins where it is not.
 */
export const AimASpell: Story = {
  args: board(scenarios.targetVariants(), { act: idleMutation(fn()) }),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    const run = journey();

    // Your main phase with something castable, so the ring is already on it.
    await waitFor(() => expect(run.at()).toBe("card:990"));

    await run.press("a");
    // Not still on the card in your hand: on something the spell can be aimed at.
    await waitFor(() => expect(run.at()).not.toBe("card:990"));
    expect(run.at(), run.trail.join("\n")).toMatch(/^(card:99[123]|act:a-charm-99[123])$/);

    await run.press("a");
    expect(args.game.act.mutate, run.trail.join("\n")).toHaveBeenCalled();
    expect(run.cost, run.trail.join("\n")).toBeLessThanOrEqual(ceiling("AimASpell"));
    expectUniqueActionIds(canvasElement);
  },
};

/**
 * `X` passes from wherever the ring is.
 *
 * Passing is the most repeated action in the game and it had no button: a
 * keyboard has had `Space` since before any of this existed, and a pad paid
 * `L2` then `A` for every priority window of every turn. `X` is empty on most
 * stops, so it takes the job rather than a button being invented for it -- and
 * the hint bar has to say so, because a bar that promises a verb the button
 * does not have is worse than a bar with nothing on it.
 */
export const PassInOnePress: Story = {
  args: board(scenarios.earlyBoard(), { act: idleMutation(fn()) }),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    const run = journey();

    const pass = args.game.actions.find((a) => a.kind === "pass");
    expect(pass, "earlyBoard is a priority window, so passing is legal").toBeDefined();

    // The bar says it before the button does it, which is the whole contract
    // between `logic/verbs.ts` and `Table.secondary`.
    await waitFor(() => expect(canvas.getByTestId("hint-bar").textContent).toContain("Pass"));

    await run.press("x");
    expect(args.game.act.mutate, run.trail.join("\n")).toHaveBeenCalledWith(pass?.id);
    expect(run.cost).toBeLessThanOrEqual(ceiling("PassInOnePress"));
  },
};

/**
 * A CREATURE TYPE IN A LIST OF HUNDREDS, WITHOUT A KEYBOARD.
 *
 * The ring opens on the first row, not the filter field: a focused field
 * raises the Deck's on-screen keyboard, and `A` there means typing with
 * nothing to type with. `up` is the field for whoever wants it; `right` pages ten rows on and
 * `left` ten back (`useCursorNav` hands the horizontal axis to the list as a
 * `padnav` event); `A` on a row chooses it, through the one Choose button.
 * Four hundred rows is forty presses end to end, and a held direction ramps.
 */
export const ChooseATypeByPaging: Story = {
  args: board(scenarios.chooseType(), { act: idleMutation(fn()) }),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    const { actions } = scenarios.chooseType();
    const options = actions.filter((a) => a.kind !== "pass");
    const run = journey();

    await waitFor(() => expect(run.at()).toBe(`combo:opt:${options[0].id}`));
    expect(document.activeElement).not.toBe(canvas.getByTestId("combo-filter"));

    await run.press("right");
    expect(run.at(), run.trail.join("\n")).toBe(`combo:opt:${options[10].id}`);
    await run.press("right");
    expect(run.at()).toBe(`combo:opt:${options[20].id}`);
    await run.press("left");
    expect(run.at()).toBe(`combo:opt:${options[10].id}`);

    // The dialog did not change size under the ring.
    const dialog = canvas.getByTestId("prompt-dialog");
    const width = dialog.getBoundingClientRect().width;
    await run.press("down");
    expect(dialog.getBoundingClientRect().width).toBe(width);

    await run.press("a");
    expect(args.game.act.mutate).toHaveBeenCalledWith(options[11].id);
    expect(run.cost).toBeLessThanOrEqual(ceiling("ChooseATypeByPaging"));
  },
};

/* ==========================================================================
   One journey per decision kind.

   The combat and priority journeys above are the ones that were measured
   first. These are the rest of the audit (`decisionAudit.ts`): every kind
   the engine raises, walked from wherever the surface that owns it puts the
   ring, so the ceiling is the whole cost a player pays and not the cost
   after a walk nobody counted.
   ========================================================================== */

/**
 * THE FIRST DECISION OF EVERY GAME IS ONE PRESS.
 *
 * `OpeningHand` lands the ring on the middle card and binds `A` on any card
 * stop to Keep (its header says why: the Keep plate is a stop too, and a
 * player reading the hand should not have to leave it to say yes).
 */
export const KeepTheHand: Story = {
  args: board(scenarios.mulligan(), { act: idleMutation(fn()) }),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("opening-hand");
    const run = journey();
    await waitFor(() => expect(run.at()).toMatch(/^card:/));

    await run.press("a");
    expect(args.game.act.mutate, run.trail.join("\n")).toHaveBeenCalledWith("a0-keep");
    expect(run.cost, run.trail.join("\n")).toBeLessThanOrEqual(ceiling("KeepTheHand"));
    expectUniqueActionIds(canvasElement);
  },
};

/**
 * ...and bottoming a card after a mulligan is one press per card, on the same
 * screen: in the bottoming phase a card's click IS the answer.
 */
export const BottomACard: Story = {
  args: board(scenarios.mulliganBottom(1), { act: idleMutation(fn()) }),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("opening-hand");
    const run = journey();
    // In the bottoming phase the cards carry the ids, so the stop is the action's.
    await waitFor(() => expect(run.at()).toMatch(/^act:a\d-bottom$/));

    await run.press("a");
    expect(args.game.act.mutate, run.trail.join("\n")).toHaveBeenCalled();
    expect(run.cost, run.trail.join("\n")).toBeLessThanOrEqual(ceiling("BottomACard"));
    expectUniqueActionIds(canvasElement);
  },
};

/**
 * A single pick in the dialog: the ring opens on the first option.
 *
 * This is the journey every `choose_objects` purpose the dialog still answers
 * is held to -- sacrifice, destroy, discard and the rest of the audit's
 * `dialog` rows -- because the dialog draws them all the same way, and the
 * press that answers one answers any.
 */
export const PickOneInTheDialog: Story = {
  args: board(scenarios.chooseTarget(), { act: idleMutation(fn()) }),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("prompt-dialog");
    const run = journey();
    await waitFor(() => expect(run.at()).toMatch(/^act:/));

    await run.press("a");
    expect(args.game.act.mutate, run.trail.join("\n")).toHaveBeenCalledWith("a0-choose");
    expect(run.cost, run.trail.join("\n")).toBeLessThanOrEqual(ceiling("PickOneInTheDialog"));
    expectUniqueActionIds(canvasElement);
  },
};

/** The same press over faces the server attached, which the player view cannot supply. */
export const PickFromTheLibrary: Story = {
  args: board(scenarios.searchLibrary(), { act: idleMutation(fn()) }),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("prompt-dialog");
    const run = journey();
    await waitFor(() => expect(run.at()).toMatch(/^act:/));

    await run.press("a");
    expect(args.game.act.mutate, run.trail.join("\n")).toHaveBeenCalledWith("a0-choose");
    expect(run.cost, run.trail.join("\n")).toBeLessThanOrEqual(ceiling("PickFromTheLibrary"));
    expectUniqueActionIds(canvasElement);
  },
};

/**
 * A SET, BUILT IN THE PANEL AND SENT ONCE.
 *
 * "Exile up to two target artifacts": `L2` jumps to the slab (in pick mode
 * the slab is the decision and the mark beside it a convenience, so that is
 * where the jump lands), `left` is the "all" mark, `A` fills the set, `right`
 * is back on the slab and `A` sends it whole through `/choose`.
 *
 * This is the ceiling `one-staged-set` is built against: `X` does not yet
 * commit a pick the way it commits an attack, which is the walk counted here.
 */
export const PickSeveralInThePanel: Story = {
  args: board(scenarios.chooseSeveralTargets(), { choose: idleMutation(fn()) }),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("pick-confirm");
    const run = journey();

    await run.press("l2");
    // The slab carries `Done`'s id, so its stop is the action's, not `commit`.
    await waitFor(() => expect(run.at()).toBe("act:a4-finish_declaration"));
    await run.walk("left", "a");
    await waitFor(() =>
      expect(canvasElement.querySelector(".commit-note")?.textContent).toMatch(/^2 chosen/),
    );
    await run.walk("right", "a");
    // Yours first, in row order: your Sol Ring and your Rhystic Study.
    expect(args.game.choose.mutate, run.trail.join("\n")).toHaveBeenCalledWith([1, 3]);
    expect(run.cost, run.trail.join("\n")).toBeLessThanOrEqual(
      ceiling("PickSeveralInThePanel"),
    );
    expectUniqueActionIds(canvasElement);
  },
};

/** A modal spell's first mode, from where the dialog opens. */
export const ChooseAMode: Story = {
  args: board(scenarios.chooseMode(), { act: idleMutation(fn()) }),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("prompt-dialog");
    const run = journey();
    await waitFor(() => expect(run.at()).toMatch(/^act:/));

    await run.press("a");
    expect(args.game.act.mutate, run.trail.join("\n")).toHaveBeenCalledWith("a0-choose");
    expect(run.cost, run.trail.join("\n")).toBeLessThanOrEqual(ceiling("ChooseAMode"));
    expectUniqueActionIds(canvasElement);
  },
};

/**
 * X = 2, THROUGH THE STEPPER.
 *
 * The one decision whose control changes which id the slab carries rather
 * than adding more (ADR 0015's deliberate exception). The panel opens with
 * the ring in the stepper, `right` is its plus, two presses raise X, `down`
 * is the slab and `A` pays. The slab's stop is the id of whatever X it
 * currently carries, which is why the walk reads the stepper's own
 * `data-x` rather than the ring.
 */
export const PayX: Story = {
  args: board(scenarios.chooseX(), { act: idleMutation(fn()) }),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("choose-x");
    const run = journey();
    await waitFor(() => expect(run.at()).toMatch(/^combo:x-/));

    await run.press("right");
    expect(run.at(), run.trail.join("\n")).toBe("combo:x-up");
    await run.walk("a", "a");
    await waitFor(() => expect(canvas.getByTestId("choose-x").dataset.x).toBe("2"));
    await run.walk("down", "a");
    expect(args.game.act.mutate, run.trail.join("\n")).toHaveBeenCalledWith("a2-choose");
    expect(run.cost, run.trail.join("\n")).toBeLessThanOrEqual(ceiling("PayX"));
    expectUniqueActionIds(canvasElement);
  },
};

/**
 * Declining a "you may" is the second option, one step from the first.
 *
 * Counted on No rather than Yes because No is the answer a player gives
 * when the trigger would hurt, and a surface that made declining a walk
 * would be a surface that taxes the right call.
 */
export const SayNo: Story = {
  args: board(scenarios.mayAbility(), { act: idleMutation(fn()) }),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("prompt-dialog");
    const run = journey();
    await waitFor(() => expect(run.at()).toBe("act:a0-choose"));

    await run.press("right");
    expect(run.at(), run.trail.join("\n")).toBe("act:a1-choose");
    await run.press("a");
    expect(args.game.act.mutate, run.trail.join("\n")).toHaveBeenCalledWith("a1-choose");
    expect(run.cost, run.trail.join("\n")).toBeLessThanOrEqual(ceiling("SayNo"));
    expectUniqueActionIds(canvasElement);
  },
};

/** Pointing at an opponent, from where the dialog opens. */
export const ChooseAPlayer: Story = {
  args: board(scenarios.choosePlayer(), { act: idleMutation(fn()) }),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("prompt-dialog");
    const run = journey();
    await waitFor(() => expect(run.at()).toMatch(/^act:/));

    await run.press("a");
    expect(args.game.act.mutate, run.trail.join("\n")).toHaveBeenCalledWith("a1-choose");
    expect(run.cost, run.trail.join("\n")).toBeLessThanOrEqual(ceiling("ChooseAPlayer"));
    expectUniqueActionIds(canvasElement);
  },
};
