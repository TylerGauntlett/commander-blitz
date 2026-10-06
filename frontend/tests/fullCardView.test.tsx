/**
 * The whole card, from a mouse.
 *
 * The rail's reader is a fixed frame on a desktop, so long rules text scrolls
 * inside a box the pointer cannot reach without leaving the card -- and leaving
 * the card empties the rail. The Deck had `Y` and `CardHold`; the desktop had
 * nothing. Right-click is its way in, on the table rather than on each card, so
 * every surface that fills the rail (a card, a plinth, a panel row, a seat's
 * commander window) opens it for free.
 */

import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Table } from "../src/components/game/Table";
import { useUiStore } from "../src/state/uiStore";
import { fakeGame } from "../src/testing/fakeGame";
import * as scenarios from "../src/testing/scenarios";

const noop = () => undefined;

afterEach(() => {
  cleanup();
  useUiStore.setState({ hoveredOid: null });
});

function renderTable() {
  const scenario = scenarios.earlyBoard();
  return render(
    <Table
      session={{ gameId: "full-card", seat: 0 }}
      state={scenario.state}
      game={fakeGame({ state: scenario.state, actions: scenario.actions })}
      onQuit={noop}
      onRematch={noop}
    />,
  );
}

/** Right-click `el`, and say whether the browser's own menu was suppressed. */
function rightClick(el: Element): boolean {
  const event = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
  act(() => {
    el.dispatchEvent(event);
  });
  return event.defaultPrevented;
}

describe("right-clicking a card", () => {
  it("opens the card under the pointer, whole, in the hold", () => {
    const { getByTestId, queryByTestId } = renderTable();
    const elves = document.querySelector('[data-stop="card:205"]') as HTMLElement;
    expect(elves).not.toBeNull();

    // What the card's own `onHoverStart` writes. Framer's hover is a
    // pointer-type gesture jsdom does not synthesise, and the rail's own tests
    // already hold that half; this file is about what the right-click does
    // with it.
    act(() => useUiStore.setState({ hoveredOid: 205 }));
    expect(queryByTestId("card-hold")).toBeNull();

    expect(rightClick(elves)).toBe(true);
    const hold = getByTestId("card-hold");
    expect(hold.getAttribute("role")).toBe("dialog");
    expect(hold.textContent).toContain("Llanowar Elves");
  });

  it("puts it down from the Close button and from the backdrop", () => {
    const { getByTestId, queryByTestId } = renderTable();
    act(() => useUiStore.setState({ hoveredOid: 205 }));

    rightClick(getByTestId("table"));
    fireEvent.click(getByTestId("card-hold-close"));
    expect(queryByTestId("card-hold")).toBeNull();

    rightClick(getByTestId("table"));
    fireEvent.click(getByTestId("card-hold"));
    expect(queryByTestId("card-hold")).toBeNull();
  });

  it("puts it down on a second right-click, though the rail still names the card", () => {
    // The hold is drawn inside the table, whose right-click is what opens it;
    // a close that bubbled up would be reopened by the same event.
    const { getByTestId, queryByTestId } = renderTable();
    act(() => useUiStore.setState({ hoveredOid: 205 }));
    rightClick(getByTestId("table"));
    rightClick(getByTestId("card-hold"));
    expect(queryByTestId("card-hold")).toBeNull();
  });

  it("leaves the browser's menu alone over nothing readable", () => {
    const { getByTestId, queryByTestId } = renderTable();
    expect(rightClick(getByTestId("table"))).toBe(false);
    expect(queryByTestId("card-hold")).toBeNull();
  });

  it("tells a desktop player it exists, in the rail's idle text", () => {
    const { getByTestId } = renderTable();
    expect(getByTestId("preview-more").textContent).toMatch(/Right-click/);
  });
});
