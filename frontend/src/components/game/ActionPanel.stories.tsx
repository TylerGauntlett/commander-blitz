/**
 * The one surface that always works.
 *
 * Three input paths converge on `act(id)` -- drag a card onto a lane, click a
 * card then click its target, or press the button here -- and only the third
 * always exists. So the panel is the floor: if a decision has no row here, the
 * game is unplayable at that moment, which is exactly the failure
 * `e2e/full-game.spec.ts` detects by running out of buttons.
 *
 * Its hard invariant is that every legal action is reachable *exactly once*.
 * `expectUniqueActionIds` is on nearly every story below, because each way of
 * breaking it -- the commit slab promoting a row it did not remove, a card's
 * target variants drawn as a row and as buttons, a modal opening without the
 * panel standing down -- is invisible in the markup that caused it.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { useUiStore } from "../../state/uiStore";
import { APP_VAR } from "../../testing/appGeometry";
import {
  expectHandheldFloors,
  expectMountedLike,
  expectUniqueActionIds,
  renderedActionIds,
  settled,
} from "../../testing/asserts";
import { pending } from "../../testing/fixtures";
import type { Scenario } from "../../testing/scenarios";
import * as scenarios from "../../testing/scenarios";
import { ActionPanel } from "./ActionPanel";

const meta = {
  title: "Game/ActionPanel",
  component: ActionPanel,
  parameters: { automtg: { mount: "railRightUnderPreviewWithFoot" } },
  args: {
    onAct: fn(),
    onStage: fn(),
    onDeclare: fn(),
    onUndo: fn(),
    onQuit: fn(),
    onToggleFullControl: fn(),
    onToggleManualMana: fn(),
    onSkipNarration: fn(),
    narrating: false,
    busy: false,
    aiThinking: false,
    standDown: false,
  },
} satisfies Meta<typeof ActionPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The two props a scenario supplies; the rest come from `meta.args`. */
const from = (scenario: Pick<Scenario, "state" | "actions">) => ({
  state: scenario.state,
  actions: scenario.actions,
});

/**
 * THE DOCK IS THE SAME SHAPE IN EVERY STATE.
 *
 * The well was always in the document and its contents were not, so between
 * decisions it collapsed to its own 18px of padding and sprang back to 66 or 90
 * when an action arrived -- and the bottom of the rail moved every time a turn
 * passed. `.preview` above it holds a constant height for exactly this reason.
 *
 * Asserted as a SHAPE and not as a pixel total, deliberately. A number here
 * would have to be either a literal duplicating `ui.css` -- which
 * `testing/appGeometry.ts`'s header is about not doing -- or the resolved `1lh`
 * of a font size the handheld floor raises. What actually has to hold is that
 * both movers are pinned: exactly one note row, exactly one bar, and neither of
 * them zero. Every state's `play` calls this, so a state that grows a second
 * row or drops one fails here rather than on a screenshot.
 */
const expectStableDock = (dock: HTMLElement) => {
  expect(dock).toBeTruthy();
  expect(dock.querySelectorAll(".commit-note")).toHaveLength(1);
  expect(dock.querySelectorAll(".bar")).toHaveLength(1);
  const note = dock.querySelector(".commit-note") as HTMLElement;
  const bar = dock.querySelector(".bar") as HTMLElement;
  // The note keeps its line with a non-breaking space when it has nothing to
  // say; a zero here is the old "the row appears when combat starts" bug.
  expect(note.getBoundingClientRect().height).toBeGreaterThan(0);
  // `.commit` and `.commit-mark` are both `min-height: 48px`.
  expect(bar.getBoundingClientRect().height).toBeGreaterThanOrEqual(48);
};

/* ------------------------------------------------------------------ */
/* Play mode                                                           */
/* ------------------------------------------------------------------ */

export const PlayMode: Story = {
  args: from(scenarios.earlyBoard()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("action-panel");
    expectUniqueActionIds(canvasElement);
  },
};

/**
 * The commit slab.
 *
 * One action is promoted out of the list into a slab of its own, and the bug
 * this catches is that it is promoted *without being removed* -- which renders
 * it twice and is invisible unless you count.
 */
export const CommitSlab: Story = {
  args: from(scenarios.earlyBoard()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const commit = await canvas.findByTestId("commit");
    expect(commit.getAttribute("data-action-id")).toBe("a0-pass");

    const ids = renderedActionIds(canvasElement);
    expectUniqueActionIds(canvasElement);
    // Present once, in the slab -- not also still sitting in the list.
    expect(ids.filter((id) => id === "a0-pass")).toHaveLength(1);
    expect(
      canvasElement.querySelectorAll('.acts__list [data-action-id="a0-pass"]'),
    ).toHaveLength(0);
  },
};

/**
 * Six ways to aim one Simic Charm.
 *
 * The engine emits one action per legal target tuple, and a row that drew the
 * card for each of them read as six copies of the same card. One row now, with
 * the ids on its target chips -- so every action stays reachable and the count
 * still comes out right.
 */
export const TargetChipsCollapsed: Story = {
  args: from(scenarios.targetVariants()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("action-panel");

    const rows = canvasElement.querySelectorAll(".acts__list .act");
    expect(rows, "three ways to aim one card should be one row").toHaveLength(1);
    expect(rows[0].getAttribute("data-action-id"), "the group row must carry no id").toBeNull();

    const chips = [...canvasElement.querySelectorAll(".act__aims .aim")];
    expect(chips.map((c) => c.textContent)).toEqual([
      "Grizzly Bears",
      "Kraken",
      "Wall of Roots",
    ]);
    expectUniqueActionIds(canvasElement);
  },
};

/** Clicking a chip submits *that* chip's action, not the row's first. */
export const ClickingATargetChip: Story = {
  args: from(scenarios.targetVariants()),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("action-panel");
    await userEvent.click(await canvas.findByText("Wall of Roots"));
    expect(args.onAct).toHaveBeenCalledWith("a-charm-993");
  },
};

/**
 * The commit slab, hovered.
 *
 * It is `width: 100%` of the rail, so it may lift but must not scale -- 1.02 of
 * a full-width element is 2% wider than the column holding it, and the button
 * grew out over the rail's edge every time the pointer crossed it. Measured
 * against the rail rather than against a number, so the assertion survives the
 * rail changing width.
 */
export const CommitSlabOnHover: Story = {
  args: from(scenarios.earlyBoard()),
  // Real motion, because the scale *is* the bug: with `reducedMotion` on, the
  // transform never applies and this assertion passed against the defect.
  parameters: { automtg: { mount: "railRightUnderPreviewWithFoot", motion: "real" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const slab = await canvas.findByTestId("commit");
    /*
     * The slab's own container, not `.rail` by name.
     *
     * What this story protects is that a `width: 100%` element does not scale
     * out of the column it is in -- and on a handheld that column is the foot,
     * because `ActionPanel` portals the dock there. Naming the rail asserted the
     * desktop arrangement as well as the invariant, and failed the moment the
     * story runner's viewport was short enough to be a handheld.
     */
    const rail = (slab.closest(".commit-dock")?.parentElement ??
      canvasElement.querySelector(".rail")) as HTMLElement;

    await userEvent.hover(slab);

    /*
     * Wait for the lift to *land*, then assert once.
     *
     * Two traps here, and this story fell into both. Wrapping the bounds check in
     * `waitFor` retries until it passes, and "inside the rail" is true at t=0 --
     * so it went green on the first poll, against the bug. And waiting for a
     * transform to merely exist returns on the spring's first frame, which reads
     * `matrix(1.0008, ...)` on its way to 1.02. Only a settled transform is worth
     * measuring.
     */
    await settled(slab);

    const button = slab.getBoundingClientRect();
    const column = rail.getBoundingClientRect();
    expect(
      Math.round(button.left),
      "the commit slab grew out past the left of its rail",
    ).toBeGreaterThanOrEqual(Math.round(column.left) - 1);
    expect(
      Math.round(button.right),
      "the commit slab grew out past the right of its rail",
    ).toBeLessThanOrEqual(Math.round(column.right) + 1);
  },
};

/** The rail is a fixed column, and the panel is what fills it. */
export const FillsTheRail: Story = {
  args: from(scenarios.earlyBoard()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("action-panel");
    const rail = canvasElement.querySelector(".rail") as HTMLElement;
    expectMountedLike(rail, { width: APP_VAR.railRight });
  },
};

/**
 * THE ANTI-JUMP GATE. Nothing is actionable, and the dock is the same height it
 * is when something is.
 *
 * The dock used to render an empty well between decisions -- 18px of padding
 * where 66 or 90 had been -- so the bottom of the rail moved every time a turn
 * passed, and moved back when the buttons returned. `.preview` above it holds a
 * constant height for exactly this reason; this asserts the dock now does too.
 *
 * Measured against `Attackers`, which is the *tallest* state (a note with a
 * count in it, and a bar of three), because a floor that only matches the
 * shortest state is not a floor at all.
 */
export const NothingToDo: Story = {
  args: from({ ...scenarios.earlyBoard(), actions: [] }),
  parameters: { automtg: { mount: "railRightUnderPreviewWithFoot" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("action-panel");
    // The idle slab stands in for the button, so the well is never visibly empty.
    await canvas.findByTestId("commit-idle");
    const dock = canvasElement.querySelector(".commit-dock") as HTMLElement;
    expectStableDock(dock);
  },
};

/* ------------------------------------------------------------------ */
/* Combat                                                              */
/* ------------------------------------------------------------------ */

/**
 * Attack mode, with two opponents.
 *
 * The branch worth posing: with more than one legal defender the ids move onto
 * the defender chips, because an attacker alone no longer identifies an action.
 */
export const AttackMode: Story = {
  args: from(scenarios.combatDeclareAttackers()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const panel = await canvas.findByTestId("combat-panel");
    expect(panel.dataset.combatKind).toBe("attackers");
    // Three attackers, two defenders each: six actions, each reachable once.
    expect(renderedActionIds(canvasElement).length).toBeGreaterThanOrEqual(6);
    expectUniqueActionIds(canvasElement);
  },
};

/**
 * WHAT A ROW PREVIEWS FOR A POINTER, IT ALSO DECLARES FOR THE RING.
 *
 * `previewing()` fills the rail on `onMouseEnter` *and* on `onFocus`, and the
 * second of those was dead: `input/cursor.ts`'s `hoverFor` runs after `stamp()`
 * has moved focus and writes `hoveredOid` itself, so a stop it could read no
 * card out of cleared the rail a beat after the row had filled it. Every action
 * row on this panel is a decision about a specific card, so on a pad the rail
 * was blank for all of them while a mouse over the same row worked.
 *
 * `data-preview-oid` is the fix and this is its gate: hover each stop, and
 * whatever the pointer put in the rail is what the attribute has to say. A row
 * that grows a new hover handler without the attribute fails here rather than
 * silently going quiet on the input that has no pointer.
 */
export const RowsDeclareWhatTheyPreview: Story = {
  args: from(scenarios.combatDeclareAttackers()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("combat-panel");

    const stops = [...canvasElement.querySelectorAll<HTMLElement>("[data-stop]")];
    expect(stops.length).toBeGreaterThan(0);
    let previewing = 0;
    for (const stop of stops) {
      useUiStore.setState({ hoveredOid: null });
      await userEvent.hover(stop);
      const byPointer = useUiStore.getState().hoveredOid;
      // Tools, the commit slab, anything that is about no card: nothing to say.
      if (byPointer === null) continue;
      previewing += 1;
      const declared = stop.dataset.previewOid;
      expect(
        declared === undefined ? null : Number(declared),
        `${stop.dataset.stop} previews ${byPointer} for a pointer and ${
          declared ?? "nothing"
        } for the ring`,
      ).toBe(byPointer);
    }
    // The walk has to have found some, or this passes by testing nothing.
    expect(previewing).toBeGreaterThan(0);
    useUiStore.setState({ hoveredOid: null });
  },
};

/** Staging is local: it goes to `onStage`, and nothing is sent until confirmed. */
export const StagingAnAttacker: Story = {
  args: from(scenarios.combatDeclareAttackers()),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("combat-panel");
    await userEvent.click(
      canvasElement.querySelector('[data-action-id="a-atk-302-1"]') as HTMLElement,
    );
    expect(args.onStage).toHaveBeenCalledWith("a-atk-302-1");
    expect(args.onAct, "staging must not reach the server").not.toHaveBeenCalled();
  },
};

/** Confirming sends the staged pairs in one declaration. */
export const ConfirmingAttacks: Story = {
  args: from(scenarios.combatDeclareAttackers()),
  parameters: {
    automtg: {
      mount: "railRightUnderPreviewWithFoot",
      ui: { stagedAttacks: { 301: 1, 302: 2 } },
    },
  },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("combat-panel");
    // The other side of `NothingToDo`'s gate: the fullest the dock ever gets --
    // a note with a count in it and a bar of three -- is the same shape as the
    // emptiest.
    expectStableDock(canvasElement.querySelector(".commit-dock") as HTMLElement);
    await userEvent.click(await canvas.findByTestId("combat-confirm"));
    expect(args.onDeclare).toHaveBeenCalledWith("attackers", [
      [301, 1],
      [302, 2],
    ]);
  },
};

/**
 * Declining combat entirely, which must still be one click.
 *
 * Note it goes through `onAct`, not `onDeclare`: attacking with nobody is the
 * engine's own `finish_declaration` action, so the client echoes that id back
 * rather than declaring an empty list of pairs. Same contract as everywhere
 * else -- the client never builds an action.
 */
export const NoAttacks: Story = {
  args: from(scenarios.combatDeclareAttackers()),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("combat-panel");
    await userEvent.click(await canvas.findByTestId("combat-skip"));
    expect(args.onAct).toHaveBeenCalledWith("a-finish");
    expect(args.onDeclare).not.toHaveBeenCalled();
  },
};

/**
 * Block mode: four attackers against three blockers.
 *
 * Sized so the suggestion tiers all have something to say -- a block can be a
 * clean kill, a trade, a chump or simply bad, and the panel grades them.
 */
export const BlockMode: Story = {
  args: from(scenarios.combatDeclareBlockers()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const panel = await canvas.findByTestId("combat-panel");
    expect(panel.dataset.combatKind).toBe("blockers");
    expectUniqueActionIds(canvasElement);
    // Incoming damage is stated, because "should I block" is a subtraction.
    expect(panel.textContent).toMatch(/\d/);
  },
};

/* ------------------------------------------------------------------ */
/* Standing down, and being gated                                      */
/* ------------------------------------------------------------------ */

/**
 * A modal owns the decision.
 *
 * Zero action ids -- otherwise the mulligan buttons exist here *and* behind the
 * dialog's backdrop, unclickable and ambiguous to anything selecting by id. The
 * tools stay in the document regardless: quitting and the stops setting are
 * wanted exactly when a dialog is up.
 */
export const StandDown: Story = {
  args: { ...from(scenarios.mulligan()), standDown: true },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("action-panel");
    expect(renderedActionIds(canvasElement)).toEqual([]);
    expect(await canvas.findByTestId("full-control")).toBeTruthy();
  },
};

/** Narration is playing: every action is gated and a skip appears. */
export const Narrating: Story = {
  args: { ...from(scenarios.earlyBoard()), narrating: true },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("action-panel");
    const cast = canvasElement.querySelector('[data-action-id="a1-cast"]');
    expect(cast?.hasAttribute("disabled")).toBe(true);
    expect(canvasElement.querySelector('[data-hint="Skip ahead"]')).toBeTruthy();
  },
};

export const AiThinking: Story = {
  args: { ...from(scenarios.earlyBoard()), aiThinking: true },
};

export const Busy: Story = {
  args: { ...from(scenarios.earlyBoard()), busy: true },
};

/** Waiting on somebody else: the prompt says who, by name. */
export const WaitingForOpponent: Story = {
  args: (() => {
    const scenario = scenarios.earlyBoard();
    scenario.state.pending = pending({ player: 1 });
    return from({ ...scenario, actions: [] });
  })(),
  parameters: { automtg: { mount: "railRightUnderPreviewWithFoot" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect((await canvas.findByTestId("prompt")).textContent).toContain("Waiting for AI 1");
    // The other half of `NothingToDo`'s gate: it is somebody else's turn, which
    // is most of the wall-clock of a four-player game, and the rail holds still
    // for all of it.
    await canvas.findByTestId("commit-idle");
    expectStableDock(canvasElement.querySelector(".commit-dock") as HTMLElement);
  },
};

/* ------------------------------------------------------------------ */
/* The tools                                                           */
/* ------------------------------------------------------------------ */

/** The toggle asks for the opposite of what the engine is currently holding. */
export const FullControlToggle: Story = {
  args: from(scenarios.earlyBoard()),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const toggle = await canvas.findByTestId("full-control");
    expect(toggle.textContent).toBe("Auto-pass");
    await userEvent.click(toggle);
    expect(args.onToggleFullControl).toHaveBeenCalledWith(true);
  },
};

export const FullControlOn: Story = {
  args: (() => {
    const scenario = scenarios.earlyBoard();
    scenario.state.full_control = true;
    return from(scenario);
  })(),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect((await canvas.findByTestId("full-control")).textContent).toBe("Full control");
  },
};

/**
 * Sound, undo and quit live behind the gear now.
 *
 * The three of them were permanent buttons in the strip at the same weight as
 * the two modes beside them, which is a row of five equally likely things when
 * two are flipped mid-turn and three are pressed once a game. The menu opens
 * UPWARDS: this strip is the last row of the panel, and below it is the commit
 * slab.
 */
export const SettingsMenu: Story = {
  args: from(scenarios.earlyBoard()),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    // Closed by default -- the whole point is that it costs no glance.
    expect(canvas.queryByTestId("settings-menu")).toBeNull();
    await userEvent.click(await canvas.findByTestId("settings"));
    expect(await canvas.findByTestId("settings-menu")).toBeTruthy();

    const before = useUiStore.getState().muted;
    await userEvent.click(await canvas.findByTestId("mute"));
    expect(useUiStore.getState().muted).toBe(!before);
    // A toggle is the one row that leaves the menu open: what you most often
    // want after flipping it is to flip it back.
    expect(canvas.queryByTestId("settings-menu")).not.toBeNull();
  },
};

/** The play rows in the compact rail: every row a 44px target, every label 16px. */
export const PlayModeHandheld: Story = {
  args: from(scenarios.earlyBoard()),
  globals: { handheld: "on" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    await settled(canvasElement);
    expectHandheldFloors(canvasElement);
  },
};

/**
 * TWO ABILITIES ON ONE CARD READ AS TWO DIFFERENT THINGS.
 *
 * The engine labels each "Mind Stone: <text>", and in a 230px row the name was
 * the only part to survive the ellipsis -- so both rows read "Mind Stone: {T}…"
 * and the player picked the sacrifice by its position. The name is one faint
 * line now and the ability wraps under it.
 */
export const AbilityRowsHandheld: Story = {
  args: from(scenarios.twoAbilityPermanent()),
  globals: { handheld: "on" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    await settled(canvasElement);
    expectHandheldFloors(canvasElement);

    const rows = [...canvasElement.querySelectorAll<HTMLElement>(".acts__list .act--ability")];
    expect(rows).toHaveLength(2);
    const names = rows.map((row) => row.querySelector(".act__name")?.textContent ?? "");
    expect(names[0]).not.toBe(names[1]);
    for (const [i, row] of rows.entries()) {
      expect(row.querySelector(".act__src")?.textContent).toBe("Mind Stone");
      expect(names[i].startsWith("Mind Stone")).toBe(false);
      // The ability's text is visible, not hidden behind the row's edge.
      const name = row.querySelector<HTMLElement>(".act__name") as HTMLElement;
      expect(name.scrollWidth, "the ability text fits its box").toBeLessThanOrEqual(
        name.clientWidth + 1,
      );
    }
    expectUniqueActionIds(canvasElement);
  },
};
