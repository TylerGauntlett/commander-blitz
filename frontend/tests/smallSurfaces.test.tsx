/**
 * Four small surfaces, characterised in jsdom.
 *
 * Each of these is drawn by a story in a real Chromium, which is where its
 * geometry is asserted. These are the parts that need no layout -- what is
 * rendered, in what order, carrying which attributes -- so they run in the
 * unit project that `scripts/verify.py --quick` reaches on a machine with no
 * browser (TECH_DEBT CG-02, UV-06).
 */

import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CardGhost, ghostTone } from "../src/components/game/CardGhost";
import { EventTicker } from "../src/components/game/EventTicker";
import { StackPanel } from "../src/components/game/StackPanel";
import { InviteDialog, inviteUrl } from "../src/components/lobby/InviteDialog";
import { resetInputMode } from "../src/input/inputMode";
import { resetPad } from "../src/input/pad";
import { useUiStore } from "../src/state/uiStore";
import * as pool from "../src/testing/cards";
import { podView } from "../src/testing/fixtures";
import { earlyBoard, ghostCard, mixedLog, stackThreeDeep } from "../src/testing/scenarios";

afterEach(cleanup);

/* ------------------------------------------------------------- StackPanel */

describe("StackPanel", () => {
  it("says the stack is empty when it is", () => {
    render(<StackPanel state={earlyBoard().state} />);
    expect(document.querySelector(".rail__empty")?.textContent).toBe("empty");
    expect(document.querySelector(".rail__badge")).toBeNull();
  });

  it("piles the items top first, badges the count, and anchors each by sid", () => {
    const { state } = stackThreeDeep();
    render(<StackPanel state={state} />);
    const plies = [...document.querySelectorAll<HTMLElement>(".stackpile__ply")];
    expect(plies.length).toBe(state.stack.length);
    expect(document.querySelector(".rail__badge")?.textContent).toBe(
      String(state.stack.length),
    );
    // Reversed: what resolves next is read first, and only it is marked.
    const sids = plies.map((p) => Number(p.dataset.stackSid));
    expect(sids).toEqual([...state.stack].reverse().map((item) => item.sid));
    expect(plies[0].className).toContain("stackpile__ply--next");
    expect(plies[0].querySelector(".stackpile__next")?.textContent).toBe("next");
    expect(plies.slice(1).some((p) => p.querySelector(".stackpile__next"))).toBe(false);
    // Each ply is a testid target and each ply below the top peeks out further.
    for (const [i, ply] of plies.entries()) {
      expect(ply.dataset.testid).toBe(`stack-item-${sids[i]}`);
      expect(ply.style.top).toBe(`${i * 26}px`);
    }
  });

  it("names the controller, the kind, and the targets in the hint", () => {
    const { state } = stackThreeDeep();
    render(<StackPanel state={state} />);
    for (const item of state.stack) {
      const ply = document.querySelector<HTMLElement>(`[data-stack-sid="${item.sid}"]`);
      expect(ply?.querySelector(".stackpile__who")?.textContent).toBe(
        state.players[item.controller].name,
      );
      expect(ply?.querySelector(".stackpile__kind") !== null).toBe(item.kind === "ability");
      expect(ply?.dataset.hint?.startsWith(item.name)).toBe(true);
      if (item.targets.length) expect(ply?.dataset.hint).toContain("→");
    }
  });

  it("gives every ply a stop the ring can stand on, and a press reaches the caller", () => {
    const { state } = stackThreeDeep();
    const onPress = vi.fn();
    render(<StackPanel state={state} onPress={onPress} />);
    for (const item of state.stack) {
      const hit = document.querySelector<HTMLElement>(`[data-stop="stack:${item.sid}"]`);
      expect(hit, `ply ${item.sid} has a stop`).not.toBeNull();
      // The reader follows the ply's card; a trigger with no card previews nothing.
      expect(hit?.dataset.previewOid).toBe(item.card ? String(item.card.oid) : undefined);
      expect(hit?.hasAttribute("data-action-id")).toBe(false);
      fireEvent.click(hit as HTMLElement);
      expect(onPress).toHaveBeenLastCalledWith(item);
    }
    expect(onPress).toHaveBeenCalledTimes(state.stack.length);
  });

  it("is still pressable with nobody listening", () => {
    const { state } = stackThreeDeep();
    render(<StackPanel state={state} />);
    const hit = document.querySelector<HTMLElement>('[data-stop="stack:1"]');
    expect(() => fireEvent.click(hit as HTMLElement)).not.toThrow();
  });

  it("draws a plate rather than a face for an item with no card", () => {
    const { state } = stackThreeDeep();
    const bare = { ...state, stack: [{ ...state.stack[0], card: null, name: "A trigger" }] };
    render(<StackPanel state={bare} />);
    expect(document.querySelector(".stackpile__ghost")?.textContent).toBe("A trigger");
    expect(document.querySelector(".stackpile .card")).toBeNull();
  });
});

/* ------------------------------------------------------------ EventTicker */

describe("EventTicker", () => {
  beforeEach(() => {
    useUiStore.setState({ logOpen: true });
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("folds the log into readable lines, and says so when there are none", () => {
    const { state } = earlyBoard();
    const { rerender } = render(<EventTicker state={state} events={[]} />);
    expect(document.querySelector(".rail__empty")?.textContent).toBe("nothing yet");
    rerender(<EventTicker state={state} events={mixedLog()} />);
    const lines = [...document.querySelectorAll(".ticker__line")].map((l) => l.textContent);
    expect(lines.length).toBeGreaterThan(0);
    expect(lines.every((l) => (l ?? "").trim().length > 0)).toBe(true);
    expect(document.querySelector(".rail__empty")).toBeNull();
  });

  it("collapses and reopens from its title, following the tail when it opens", () => {
    const { state } = earlyBoard();
    render(<EventTicker state={state} events={mixedLog()} />);
    expect(document.querySelector(".ticker__lines")).not.toBeNull();
    act(() => {
      fireEvent.click(document.querySelector(".rail__title--button") as HTMLElement);
    });
    expect(useUiStore.getState().logOpen).toBe(false);
    expect(document.querySelector(".rail__chevron")?.textContent).toBe("▸");
    act(() => {
      fireEvent.click(document.querySelector(".rail__title--button") as HTMLElement);
    });
    expect(useUiStore.getState().logOpen).toBe(true);
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it("keeps only the last two hundred lines", () => {
    const { state } = earlyBoard();
    const one = mixedLog().find((e) => e.type === "draw") ?? mixedLog()[0];
    const events = Array.from({ length: 260 }, () => ({ ...one }));
    render(<EventTicker state={state} events={events} />);
    expect(document.querySelectorAll(".ticker__line").length).toBeLessThanOrEqual(200);
  });
});

/* -------------------------------------------------------------- CardGhost */

describe("CardGhost", () => {
  it("reads every destination as one of five tones", () => {
    expect(ghostTone("exile")).toBe("exile");
    expect(ghostTone("hand")).toBe("hand");
    expect(ghostTone("command")).toBe("command");
    expect(ghostTone("library")).toBe("library");
    expect(ghostTone("graveyard")).toBe("graveyard");
    expect(ghostTone("battlefield")).toBe("graveyard");
  });

  const flight = {
    from: { x: 10, y: 20 },
    toPoint: { x: 200, y: 300 },
    width: 120,
    duration: 1.2,
    delay: 0,
  };

  it("carries its oid, destination and observed width, and the caption", () => {
    render(
      <CardGhost
        oid={77}
        card={ghostCard()}
        name="Whatever"
        caption="Destroyed by Vandalblast"
        to="graveyard"
        cause="destroyed"
        {...flight}
      />,
    );
    const ghost = document.querySelector<HTMLElement>("[data-testid='card-ghost']");
    expect(ghost?.dataset.ghostOid).toBe("77");
    expect(ghost?.dataset.ghostTo).toBe("graveyard");
    expect(ghost?.className).toBe("fx-ghost fx-ghost--graveyard");
    expect(ghost?.style.left).toBe("10px");
    expect(ghost?.style.top).toBe("20px");
    expect(ghost?.style.getPropertyValue("--card-w")).toBe("120px");
    expect(ghost?.querySelector(".fx-ghost__cause")?.textContent).toBe(
      "Destroyed by Vandalblast",
    );
    // A real card: its face, with the wash inside it so the caption stays clear.
    expect(ghost?.querySelector(".fx-ghost__card .card__pivot .face")).not.toBeNull();
    expect(ghost?.querySelector(".fx-ghost__card .fx-ghost__wash")).not.toBeNull();
    expect(ghost?.querySelector(".fx-ghost__plate")).toBeNull();
  });

  it("draws a name plate for a token, which has no card left to draw", () => {
    render(
      <CardGhost
        oid={5}
        card={null}
        name="Zombie"
        caption="Sacrificed"
        to="exile"
        {...flight}
      />,
    );
    const ghost = document.querySelector<HTMLElement>("[data-testid='card-ghost']");
    expect(ghost?.className).toBe("fx-ghost fx-ghost--exile");
    expect(ghost?.querySelector(".fx-ghost__plate")?.textContent).toBe("Zombie");
    expect(ghost?.querySelector(".face")).toBeNull();
  });

  it("does not need a cause to be legible", () => {
    render(
      <CardGhost
        oid={5}
        card={pool.llanowarElves({ oid: 5 })}
        name="x"
        caption="Left"
        to="hand"
        {...flight}
      />,
    );
    expect(document.querySelector(".fx-ghost--hand")).not.toBeNull();
  });
});

/* ----------------------------------------------------------- InviteDialog */

describe("InviteDialog", () => {
  const pod = (seats = 0) =>
    podView(
      [
        { kind: "human", is_you: true, is_host: true, name: "You" },
        ...Array.from({ length: seats }, () => ({ kind: "open" as const })),
      ],
      { code: "GYRE-8412", invite_link: "/pods/GYRE-8412" },
    );

  beforeEach(() => {
    vi.useFakeTimers();
    (navigator as unknown as { getGamepads: () => unknown[] }).getGamepads = () => [];
  });
  afterEach(() => {
    resetPad();
    resetInputMode();
    vi.useRealTimers();
  });

  it("builds the link from the browser's own location, not the server's", () => {
    expect(inviteUrl(pod())).toBe(new URL("/pods/GYRE-8412", window.location.href).toString());
  });

  it("shows the code and the link, each with its own copy button, inside a modal root", () => {
    render(
      <InviteDialog pod={pod()} onClose={() => undefined} onOpenChair={() => undefined} />,
    );
    const dialog = document.querySelector<HTMLElement>("[data-testid='invite-dialog']");
    expect(dialog?.hasAttribute("data-modal-root")).toBe(true);
    expect(dialog?.getAttribute("role")).toBe("dialog");
    expect(document.querySelector("[data-testid='invite-code']")?.textContent).toBe(
      "GYRE-8412",
    );
    expect(document.querySelector("[data-testid='invite-link']")?.textContent).toContain(
      "/pods/GYRE-8412",
    );
    expect([...document.querySelectorAll(".inv__code .btn")].map((b) => b.textContent)).toEqual(
      ["Copy", "Copy"],
    );
  });

  it("confirms a copy for a moment, then reverts -- and survives a refused clipboard", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("not secure"));
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(
      <InviteDialog pod={pod()} onClose={() => undefined} onOpenChair={() => undefined} />,
    );
    const [copyCode, copyLink] =
      document.querySelectorAll<HTMLButtonElement>(".inv__code .btn");
    await act(async () => {
      fireEvent.click(copyCode);
    });
    expect(writeText).toHaveBeenCalledWith("GYRE-8412");
    expect(copyCode.textContent).toBe("Copied");
    expect(copyLink.textContent).toBe("Copy");
    act(() => {
      vi.advanceTimersByTime(1700);
    });
    expect(copyCode.textContent).toBe("Copy");
  });

  it("offers to open a chair when none is open, and to go back when one is", () => {
    const onOpenChair = vi.fn();
    const onClose = vi.fn();
    const { rerender } = render(
      <InviteDialog pod={pod(0)} onClose={onClose} onOpenChair={onOpenChair} />,
    );
    expect(document.querySelector(".inv__note")?.textContent).toMatch(/Open one to hold it/);
    fireEvent.click(document.querySelector(".inv__foot .btn") as HTMLElement);
    expect(onOpenChair).toHaveBeenCalledTimes(1);

    rerender(<InviteDialog pod={pod(2)} onClose={onClose} onOpenChair={onOpenChair} />);
    expect(document.querySelector(".inv__note")?.textContent).toMatch(/^2 chairs are open/);
    fireEvent.click(document.querySelector(".inv__foot .btn") as HTMLElement);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes from the veil, the X, and Escape", () => {
    const onClose = vi.fn();
    render(<InviteDialog pod={pod()} onClose={onClose} onOpenChair={() => undefined} />);
    fireEvent.click(document.querySelector(".veil--invite") as HTMLElement);
    fireEvent.click(document.querySelector(".inv__x") as HTMLElement);
    expect(onClose).toHaveBeenCalledTimes(2);
    // Escape reaches `useDismiss` through the pad layer, which answers a frame
    // later from its poll loop (`lobbyBack.test.tsx` walks the same path).
    fireEvent.keyDown(window, { key: "Escape" });
    act(() => {
      vi.advanceTimersByTime(50);
    });
    expect(onClose).toHaveBeenCalledTimes(3);
  });
});
