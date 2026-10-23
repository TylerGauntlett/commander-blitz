/**
 * "Any number of target permanents" as a set built in the action panel.
 *
 * The playtest reports, in order: the dialog listed every PAIR as one text
 * button, both sides of the table mixed -- then a spell's "any number" was one
 * cast row per subset, a column of "A + B + C" chips capped at twelve. Now the
 * engine asks for the set as the cast happens and the panel answers it the
 * way an attack is declared: a row per candidate, an "all" mark, and one slab
 * that commits the set through `onChoose` in one request.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActionPanel } from "../src/components/game/ActionPanel";
import { isModalDecision, PromptDialog } from "../src/components/game/PromptDialog";
import { boardPickAction, isBoardPick } from "../src/logic/pickSeveral";
import { useUiStore } from "../src/state/uiStore";
import { expectUniqueActionIds } from "../src/testing/asserts";
import { chooseSeveralTargets, chooseTarget, discardACard } from "../src/testing/scenarios";

afterEach(() => {
  cleanup();
  useUiStore.getState().clearStaging();
});

const noop = () => undefined;

function renderPick(onChoose = vi.fn(), onAct = vi.fn()) {
  const { state, actions } = chooseSeveralTargets();
  render(
    <ActionPanel
      state={state}
      actions={actions}
      onAct={onAct}
      onStage={noop}
      onDeclare={noop}
      onChoose={onChoose}
      onUndo={noop}
      onQuit={noop}
      onToggleFullControl={noop}
      onToggleManualMana={noop}
      narrating={false}
      onSkipNarration={noop}
      busy={false}
      aiThinking={false}
      standDown={false}
    />,
  );
  const toggles = () => screen.getAllByTestId("pick-option");
  return {
    toggles,
    confirm: () => screen.getByTestId("pick-confirm"),
    all: () => screen.getByTestId("pick-all"),
    onChoose,
    onAct,
  };
}

/** The oid a row stands for, off the preview it carries. */
function oidOf(el: HTMLElement): number {
  return Number(el.getAttribute("data-preview-oid"));
}

const pressed = (el: HTMLElement) => el.getAttribute("aria-pressed") === "true";

describe("it is the panel's, not a dialog's", () => {
  it("the panel is in pick mode", () => {
    renderPick();
    expect(screen.getByTestId("action-panel").getAttribute("data-mode")).toBe("pick");
  });

  it("the dialog stands aside", () => {
    const { state, actions } = chooseSeveralTargets();
    render(<PromptDialog state={state} actions={actions} onAct={noop} disabled={false} />);
    expect(screen.queryByTestId("prompt-dialog")).toBeNull();
  });
});

describe("each candidate is one row", () => {
  it("draws one row per candidate, yours first", () => {
    const { toggles } = renderPick();
    expect(toggles().map(oidOf)).toEqual([801, 802, 811, 812]);
  });

  it("the rows are stops, not actions; Confirm is the only action", () => {
    const { toggles, confirm } = renderPick();
    for (const toggle of toggles()) {
      expect(toggle.hasAttribute("data-action-id")).toBe(false);
      expect(toggle.getAttribute("data-stop")).toMatch(/^combo:pick:/);
    }
    expect(confirm().getAttribute("data-action-id")).toBe("a4-finish_declaration");
    expectUniqueActionIds(document.body);
  });
});

describe("toggling", () => {
  it("a press turns a row on, and a second press turns it off", () => {
    const { toggles } = renderPick();
    fireEvent.click(toggles()[0]);
    expect(pressed(toggles()[0])).toBe(true);
    fireEvent.click(toggles()[0]);
    expect(pressed(toggles()[0])).toBe(false);
  });

  it("stops at the ceiling: the rest dim, the chosen stay pressable", () => {
    const { toggles } = renderPick();
    fireEvent.click(toggles()[0]);
    fireEvent.click(toggles()[2]);
    const rows = toggles() as HTMLButtonElement[];
    expect(rows[1].disabled).toBe(true);
    expect(rows[3].disabled).toBe(true);
    expect(rows[0].disabled).toBe(false);
  });

  it("nothing is sent while choosing", () => {
    const { toggles, onChoose, onAct } = renderPick();
    fireEvent.click(toggles()[0]);
    fireEvent.click(toggles()[2]);
    expect(onChoose).not.toHaveBeenCalled();
    expect(onAct).not.toHaveBeenCalled();
  });
});

describe("the all mark", () => {
  it("fills the set in row order, up to the ceiling", () => {
    const { toggles, all } = renderPick();
    fireEvent.click(all());
    expect(toggles().map(pressed)).toEqual([true, true, false, false]);
  });

  it("keeps what is already chosen", () => {
    const { toggles, all } = renderPick();
    fireEvent.click(toggles()[3]);
    fireEvent.click(all());
    expect(toggles().map(pressed)).toEqual([true, false, false, true]);
  });

  it("pressed on a full set, it empties it", () => {
    const { toggles, all } = renderPick();
    fireEvent.click(all());
    fireEvent.click(all());
    expect(toggles().map(pressed)).toEqual([false, false, false, false]);
  });
});

describe("confirming", () => {
  it("sends the option ordinals of exactly the rows left on", () => {
    const { toggles, confirm, onChoose } = renderPick();
    fireEvent.click(toggles()[1]); // your Rhystic Study, option 3
    fireEvent.click(toggles()[2]); // their Rhystic Study, option 0
    fireEvent.click(toggles()[1]); // changed your mind
    fireEvent.click(toggles()[3]); // their Sol Ring, option 2
    fireEvent.click(confirm());
    expect(onChoose).toHaveBeenCalledWith([0, 2]);
  });

  it("with nothing on, it chooses none", () => {
    const { confirm, onChoose } = renderPick();
    expect(confirm().textContent).toBe("Choose none");
    fireEvent.click(confirm());
    expect(onChoose).toHaveBeenCalledWith([]);
  });

  it("says how many it would send", () => {
    const { toggles, confirm } = renderPick();
    fireEvent.click(toggles()[0]);
    expect(confirm().textContent).toBe("Confirm 1");
  });
});

describe("a single pick off the table", () => {
  it("is still the dialog, answered with one press", () => {
    const { state, actions } = discardACard();
    const onAct = vi.fn();
    render(<PromptDialog state={state} actions={actions} onAct={onAct} disabled={false} />);
    const first = document.querySelector<HTMLElement>(".opt--card");
    expect(first?.querySelector(".opt__caption")).toBeNull();
    if (first) fireEvent.click(first);
    expect(onAct).toHaveBeenCalledWith("a0-choose");
  });
});

/**
 * "Sacrifice a creature": one pick of a permanent, which the board answers.
 *
 * The dialog stands down, the panel mirrors every option as a row carrying the
 * option's own `choose` id -- once, so the exactly-once invariant holds -- and
 * a press on the row is the answer.
 */
describe("a single pick of a permanent", () => {
  it("is not the dialog's", () => {
    const { state } = chooseTarget();
    expect(isBoardPick(state)).toBe(true);
    expect(isModalDecision(state)).toBe(false);
    // Nor anything off the table, nor a set.
    expect(isBoardPick(discardACard().state)).toBe(false);
    expect(isBoardPick(chooseSeveralTargets().state)).toBe(false);
  });

  it("is mirrored in the panel, one row per option carrying its id", () => {
    const { state, actions } = chooseTarget();
    const onAct = vi.fn();
    render(
      <ActionPanel
        state={state}
        actions={actions}
        onAct={onAct}
        onStage={noop}
        onDeclare={noop}
        onChoose={noop}
        onUndo={noop}
        onQuit={noop}
        onToggleFullControl={noop}
        onToggleManualMana={noop}
        narrating={false}
        onSkipNarration={noop}
        busy={false}
        aiThinking={false}
        standDown={false}
      />,
    );
    const rows = screen.getAllByTestId("pick-one");
    expect(rows.map((row) => row.dataset.actionId)).toEqual([
      "a0-choose",
      "a1-choose",
      "a2-choose",
    ]);
    expectUniqueActionIds(document.body);
    fireEvent.click(rows[1]);
    expect(onAct).toHaveBeenCalledWith("a1-choose");
  });

  it("finds the action a press on each card answers with", () => {
    const { state, actions } = chooseTarget();
    expect(boardPickAction(state, actions, 902)?.id).toBe("a1-choose");
    expect(boardPickAction(state, actions, 999)).toBeNull();
  });
});
