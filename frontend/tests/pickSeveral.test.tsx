/**
 * "Choose up to two target artifacts and/or enchantments" as cards to toggle.
 *
 * The playtest report: the dialog listed every PAIR as one text button, both
 * sides of the table mixed, no art -- and the pair you wanted was often not on
 * the list. Now each candidate is a card, on and off, and Confirm commits the
 * set through `onChoose` in one request.
 */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PromptDialog } from "../src/components/game/PromptDialog";
import { expectUniqueActionIds } from "../src/testing/asserts";
import { chooseSeveralTargets, chooseTarget } from "../src/testing/scenarios";

afterEach(cleanup);

function renderPick(onChoose = vi.fn(), onAct = vi.fn()) {
  const { state, actions } = chooseSeveralTargets();
  render(
    <PromptDialog
      state={state}
      actions={actions}
      onAct={onAct}
      onChoose={onChoose}
      disabled={false}
    />,
  );
  const grid = screen.getByTestId("pick-several");
  const toggles = within(grid).getAllByRole("button");
  return { toggles, confirm: screen.getByTestId("pick-confirm"), onChoose, onAct };
}

/** The oid a toggle stands for, off its `card:<oid>` stop. */
function oidOf(el: HTMLElement): number {
  return Number(el.getAttribute("data-stop")?.split(":")[1]);
}

describe("each candidate is one card", () => {
  it("draws one toggle per candidate, as a card face and no caption", () => {
    const { toggles } = renderPick();
    expect(toggles).toHaveLength(4);
    for (const toggle of toggles) {
      expect(toggle.querySelector(".face")).not.toBeNull();
      expect(toggle.querySelector(".opt__caption")).toBeNull();
    }
  });

  it("puts yours first", () => {
    const { toggles } = renderPick();
    expect(toggles.map(oidOf)).toEqual([801, 802, 811, 812]);
  });

  it("the toggles are stops, not actions; Confirm is the only action", () => {
    const { toggles, confirm } = renderPick();
    for (const toggle of toggles) expect(toggle.hasAttribute("data-action-id")).toBe(false);
    expect(confirm.getAttribute("data-action-id")).toBe("a4-finish_declaration");
    expectUniqueActionIds(document.body);
  });
});

describe("toggling", () => {
  it("a press turns a card on, and a second press turns it off", () => {
    const { toggles } = renderPick();
    fireEvent.click(toggles[0]);
    expect(toggles[0].getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(toggles[0]);
    expect(toggles[0].getAttribute("aria-pressed")).toBe("false");
  });

  it("stops at the ceiling: the rest dim, the chosen stay pressable", () => {
    const { toggles } = renderPick();
    fireEvent.click(toggles[0]);
    fireEvent.click(toggles[2]);
    expect((toggles[1] as HTMLButtonElement).disabled).toBe(true);
    expect((toggles[3] as HTMLButtonElement).disabled).toBe(true);
    expect((toggles[0] as HTMLButtonElement).disabled).toBe(false);
  });

  it("nothing is sent while choosing", () => {
    const { toggles, onChoose, onAct } = renderPick();
    fireEvent.click(toggles[0]);
    fireEvent.click(toggles[2]);
    expect(onChoose).not.toHaveBeenCalled();
    expect(onAct).not.toHaveBeenCalled();
  });
});

describe("confirming", () => {
  it("sends the option ordinals of exactly the cards left on", () => {
    const { toggles, confirm, onChoose } = renderPick();
    fireEvent.click(toggles[1]); // your Rhystic Study, option 3
    fireEvent.click(toggles[2]); // their Rhystic Study, option 0
    fireEvent.click(toggles[1]); // changed your mind
    fireEvent.click(toggles[3]); // their Sol Ring, option 2
    fireEvent.click(confirm);
    expect(onChoose).toHaveBeenCalledWith([0, 2]);
  });

  it("with nothing on, it chooses none", () => {
    const { confirm, onChoose } = renderPick();
    expect(confirm.textContent).toBe("Choose none");
    fireEvent.click(confirm);
    expect(onChoose).toHaveBeenCalledWith([]);
  });
});

describe("a single pick is unchanged", () => {
  it("still answers with one press, and drops the caption that repeats the name", () => {
    const { state, actions } = chooseTarget();
    const onAct = vi.fn();
    render(
      <PromptDialog
        state={state}
        actions={actions}
        onAct={onAct}
        onChoose={vi.fn()}
        disabled={false}
      />,
    );
    expect(screen.queryByTestId("pick-several")).toBeNull();
    const first = document.querySelector<HTMLElement>(".opt--card");
    expect(first?.querySelector(".opt__caption")).toBeNull();
    if (first) fireEvent.click(first);
    expect(onAct).toHaveBeenCalledWith("a0-choose");
  });
});
