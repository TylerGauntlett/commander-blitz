/**
 * An opponent's board, held open on R2.
 *
 * The component is a reader: it draws one opponent's mat at a fixed, generous
 * card size and nothing on it can be pressed. Two invariants matter to the
 * rest of the client and are pinned here. It never puts a second `data-player`
 * or `life-<pid>` in the document (`FxLayer` anchors by `querySelector` and
 * would hit whichever came first), and it never carries a `data-action-id`
 * (`ActionPanel`'s exactly-once invariant). TECH_DEBT CG-02 / LP-03.
 *
 * LP-03 also names what this surface does NOT yet do, and one of those is
 * pinned as a known failure rather than fixed: it renders no `data-modal-root`,
 * so the ring is free to walk the board underneath it. The `B`-to-close half
 * of the same finding lives in `Table`'s unwind ladder, not here.
 */

import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { OpponentBoard } from "../src/components/game/OpponentBoard";
import { earlyBoard, fourPlayerPod } from "../src/testing/scenarios";

afterEach(cleanup);

const board = () => document.querySelector<HTMLElement>("[data-testid='opponent-board']");

describe("OpponentBoard", () => {
  it("renders nothing when nothing is held", () => {
    const { container } = render(<OpponentBoard state={earlyBoard().state} pid={null} />);
    expect(container.innerHTML).toBe("");
  });

  it("renders nothing for a seat that does not exist", () => {
    const { container } = render(<OpponentBoard state={earlyBoard().state} pid={9} />);
    expect(container.innerHTML).toBe("");
  });

  it("names the seat and its life in the head, and draws their lanes in full", () => {
    const { state } = earlyBoard();
    render(<OpponentBoard state={state} pid={1} />);
    const opponent = state.players[1];
    expect(board()?.querySelector(".oppboard__who")?.textContent).toBe(opponent.name);
    expect(board()?.querySelector(".oppboard__life")?.textContent).toBe(String(opponent.life));
    // The mat, not compact: every lane of theirs is a full band.
    expect(board()?.querySelector(".mat--compact")).toBeNull();
    expect(board()?.querySelectorAll(".lane").length).toBeGreaterThan(0);
    expect(board()?.getAttribute("aria-live")).toBe("polite");
  });

  it("is a reader: no action ids, no second orb, no second life total", () => {
    const { state } = fourPlayerPod();
    render(<OpponentBoard state={state} pid={2} />);
    expect(board()?.querySelectorAll("[data-action-id]").length).toBe(0);
    expect(board()?.querySelectorAll("[data-player]").length).toBe(0);
    expect(board()?.querySelectorAll("[data-testid^='life-']").length).toBe(0);
    expect(board()?.querySelector(".orb")).toBeNull();
  });

  it("follows the seat it is handed", () => {
    const { state } = fourPlayerPod();
    const { rerender } = render(<OpponentBoard state={state} pid={1} />);
    expect(board()?.querySelector(".oppboard__who")?.textContent).toBe(state.players[1].name);
    rerender(<OpponentBoard state={state} pid={3} />);
    expect(board()?.querySelector(".oppboard__who")?.textContent).toBe(state.players[3].name);
    rerender(<OpponentBoard state={state} pid={null} />);
    expect(board()).toBeNull();
  });

  // LP-03: a full-screen overlay that does not trap the ring. Flips to a
  // passing test the day it becomes a modal; until then this documents the gap.
  it.fails("LP-03: traps the ring with a modal root while it is up", () => {
    render(<OpponentBoard state={earlyBoard().state} pid={1} />);
    expect(board()?.hasAttribute("data-modal-root")).toBe(true);
  });
});
