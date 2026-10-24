/**
 * The board's attribute contract, pinned.
 *
 * Everything that drives the table from outside -- the focus ring, the pad
 * bindings, the hint bar, the e2e suite, `stops.test.tsx` -- reads the DOM by
 * attribute: `data-testid`, `data-stop`, `data-action-id`, `data-preview-oid`,
 * `data-modal-root`, `data-hint`, `data-action-kind`. None of it reads a
 * component name. So a restructuring of `Table` or `ActionPanel` into smaller
 * files is correct exactly when the ordered list of those attributes, for the
 * same position, is byte-identical -- and that is what these snapshots hold.
 *
 * WHAT A DIFF HERE MEANS. A changed snapshot after a pure move is a bug in the
 * move. A changed snapshot after a deliberate change to the board is the review
 * asking "did you mean to move this stop?" -- update it with `vitest -u` in the
 * same commit and say so. Either way, nothing here asserts a value: the
 * snapshot is the assertion.
 *
 * Both layouts, because the compact board renders different nodes (the foot
 * tools are portaled, the opponent boards collapse), not just different CSS.
 * jsdom has no `matchMedia`, so the handheld layout is chosen the way the
 * Storybook preview chooses it: by the attribute on `<html>`.
 */

import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ActionPanel } from "../src/components/game/ActionPanel";
import { Table } from "../src/components/game/Table";
import { fakeGame } from "../src/testing/fakeGame";
import type { Scenario } from "../src/testing/scenarios";
import * as scenarios from "../src/testing/scenarios";

const ATTRIBUTES = [
  "data-testid",
  "data-stop",
  "data-action-id",
  "data-action-kind",
  "data-preview-oid",
  "data-modal-root",
  "data-hint",
] as const;

/** Every element carrying any of the attributes, in document order, one line each. */
function shape(): string[] {
  const lines: string[] = [];
  for (const el of document.body.querySelectorAll<HTMLElement>("*")) {
    const parts = ATTRIBUTES.filter((a) => el.hasAttribute(a)).map(
      (a) =>
        `${a.slice(5)}=${el.getAttribute(a) === "" ? "" : JSON.stringify(el.getAttribute(a))}`,
    );
    if (parts.length) lines.push(`${el.tagName.toLowerCase()} ${parts.join(" ")}`);
  }
  return lines;
}

const POSITIONS: Record<string, () => Scenario> = {
  openingHand: scenarios.openingHand,
  earlyBoard: scenarios.earlyBoard,
  combatDeclareAttackers: scenarios.combatDeclareAttackers,
  combatDeclareBlockers: scenarios.combatDeclareBlockers,
  stackThreeDeep: scenarios.stackThreeDeep,
  fourPlayerPod: scenarios.fourPlayerPod,
  chooseTarget: scenarios.chooseTarget,
  chooseMode: scenarios.chooseMode,
  targetVariants: scenarios.targetVariants,
  gameOver: () => scenarios.gameOver(0),
};

const noop = () => undefined;

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-compact");
  document.documentElement.removeAttribute("data-layout");
});

describe.each(["desktop", "handheld"] as const)("Table, %s layout", (layout) => {
  it.each(Object.keys(POSITIONS))("%s", (name) => {
    document.documentElement.setAttribute("data-layout", layout);
    document.documentElement.toggleAttribute("data-compact", layout !== "desktop");
    const scenario = POSITIONS[name]();
    render(
      <Table
        session={{ gameId: "shape", seat: 0 }}
        state={scenario.state}
        game={fakeGame({ state: scenario.state, actions: scenario.actions })}
        onQuit={noop}
        onRematch={noop}
      />,
    );
    expect(shape()).toMatchSnapshot();
  });
});

describe("ActionPanel alone, one snapshot per mode", () => {
  const base = {
    onStage: noop,
    onChoose: noop,
    onDeclare: noop,
    onUndo: noop,
    onQuit: noop,
    onSkipNarration: noop,
    narrating: false,
    busy: false,
    aiThinking: false,
    onToggleFullControl: noop,
    onToggleManualMana: noop,
    standDown: false,
    onAct: noop,
  };
  const modes = {
    play: scenarios.earlyBoard,
    attack: scenarios.combatDeclareAttackers,
    block: scenarios.combatDeclareBlockers,
    variants: scenarios.targetVariants,
    twoAbilities: scenarios.twoAbilityPermanent,
  };
  it.each(Object.keys(modes) as (keyof typeof modes)[])("%s", (mode) => {
    const scenario = modes[mode]();
    render(<ActionPanel {...base} state={scenario.state} actions={scenario.actions} />);
    expect(shape()).toMatchSnapshot();
  });
});
