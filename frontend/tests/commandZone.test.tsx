/**
 * The commander plinth as a *preview* surface.
 *
 * `CommandZone`'s own docstring has always said "the full card is one hover away
 * in the preview rail", and it was not true. The plinth was rendered with
 * `disabled={disabled || !castable}`, browsers dispatch no mouse events over a
 * disabled control, and every plinth but a castable one is disabled -- so the
 * rail stayed empty for an opponent's commander, for a commander on the
 * battlefield, and for your own whenever you could not cast it right now, which
 * is nearly always.
 *
 * That is a one-word regression to reintroduce and nothing on screen would look
 * wrong, so it is asserted here per state rather than left to the e2e run.
 */

import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { CardView, GameView } from "../src/api/types";
import { CommandZone } from "../src/components/game/CommandZone";
import { useUiStore } from "../src/state/uiStore";
import { card, gameView, player } from "./fixtures";

afterEach(() => {
  cleanup();
  useUiStore.setState({ images: null, hoveredOid: null });
});

function commander(overrides: Partial<CardView> = {}): CardView {
  return card({
    oid: 99,
    name: "Aesi, Tyrant of Gyre Strait",
    mana_cost: "{4}{G}{U}",
    is_commander: true,
    zone: "command",
    ...overrides,
  });
}

/** A view whose seat 0 owns `cards`, wherever those cards say they are. */
function viewWith(cards: CardView[], view: Partial<GameView> = {}): GameView {
  const zone = (name: CardView["zone"]) => cards.filter((c) => c.zone === name);
  return gameView({
    players: [
      player({
        pid: 0,
        command: zone("command"),
        graveyard: zone("graveyard"),
        exile: zone("exile"),
      }),
      player({ pid: 1, name: "AI 1", hand: null }),
    ],
    battlefield: zone("battlefield"),
    ...view,
  });
}

interface Options {
  playable?: number[];
  compact?: boolean;
  disabled?: boolean;
  seal?: React.ReactNode;
}

function renderZone(cards: CardView[], options: Options = {}, view: Partial<GameView> = {}) {
  const hovered: (number | null)[] = [];
  const result = render(
    <CommandZone
      state={viewWith(cards, view)}
      pid={0}
      playableOids={new Set(options.playable ?? [])}
      compact={options.compact}
      disabled={options.disabled}
      seal={options.seal}
      onHover={(oid) => hovered.push(oid)}
    />,
  );
  return { ...result, hovered };
}

describe("hovering a plinth fills the preview rail", () => {
  /* One case per commander state, because the bug was per state: the ready
     plinth worked and every other one silently did not. */
  const STATES: [string, Partial<CardView>, number[]][] = [
    ["ready", { zone: "command" }, [99]],
    ["waiting in the command zone", { zone: "command" }, []],
    ["on the battlefield", { zone: "battlefield" }, []],
    ["in the graveyard", { zone: "graveyard" }, []],
    ["exiled", { zone: "exile" }, []],
  ];

  it.each(STATES)("reports the hover when %s", (_label, overrides, playable) => {
    const { getByTestId, hovered } = renderZone([commander(overrides)], { playable });
    const slot = getByTestId("commander-99");
    fireEvent.mouseEnter(slot);
    expect(hovered).toEqual([99]);
    fireEvent.mouseLeave(slot);
    expect(hovered).toEqual([99, null]);
  });

  it("reports the hover on an opponent's compact plinth", () => {
    // You never cast from one, so it was permanently disabled -- and reading an
    // opponent's commander is most of why you look at their panel at all.
    const { getByTestId, hovered } = renderZone([commander()], { compact: true });
    fireEvent.mouseEnter(getByTestId("commander-99"));
    expect(hovered).toEqual([99]);
  });

  it("reports the hover while input is locked", () => {
    // `disabled` is the narration gate. Narration is exactly when a player has
    // time to read something.
    const { getByTestId, hovered } = renderZone([commander()], {
      playable: [99],
      disabled: true,
    });
    fireEvent.mouseEnter(getByTestId("commander-99"));
    expect(hovered).toEqual([99]);
  });

  it("reports the hover from the keyboard as well as the pointer", () => {
    // The same pairing `ActionPanel.previewing()` uses. A plinth that is not a
    // disabled control is focusable, so this costs nothing to support.
    const { getByTestId, hovered } = renderZone([commander()]);
    const slot = getByTestId("commander-99");
    fireEvent.focus(slot);
    fireEvent.blur(slot);
    expect(hovered).toEqual([99, null]);
  });
});

describe("clearing a hover the plinth can no longer own", () => {
  it("clears the preview when the hovered plinth unmounts", () => {
    // `hoveredOid` is otherwise only ever cleared by an element's own leave
    // handler, so a commander shuffled back into the library while hovered pins
    // the rail to a card nobody is pointing at -- mockup-fidelity.md defect #4.
    useUiStore.setState({ hoveredOid: 99 });
    const { unmount, hovered } = renderZone([commander()]);
    unmount();
    expect(hovered).toEqual([null]);
  });

  it("leaves a hover that has already moved somewhere else alone", () => {
    // By the time a plinth unmounts the pointer may be on a card in hand.
    // Clearing then would blank a preview that is correct.
    useUiStore.setState({ hoveredOid: 42 });
    const { unmount, hovered } = renderZone([commander()]);
    unmount();
    expect(hovered).toEqual([]);
  });
});

describe("what the plinth still refuses to do", () => {
  it("announces its state without becoming an unhoverable control", () => {
    const { getByTestId } = renderZone([commander()]);
    const slot = getByTestId("commander-99") as HTMLButtonElement;
    expect(slot.getAttribute("aria-disabled")).toBe("true");
    expect(slot.disabled).toBe(false);
  });

  it("carries no action id, in any state", () => {
    // A gesture surface like the hand. The action panel keeps sole ownership of
    // the id; e2e/cycle3.spec.ts and e2e/action-panel.spec.ts both assert it.
    const { getByTestId } = renderZone([commander()], { playable: [99] });
    const slot = getByTestId("commander-99");
    expect(slot.getAttribute("data-action-id")).toBeNull();
    expect(slot.querySelector("[data-action-id]")).toBeNull();
  });
});

describe("the life seal", () => {
  it("hands the seal to the portrait's frame, not to a row of its own", () => {
    const { container } = renderZone([commander()], {
      seal: <div data-testid="seal-under-test" />,
    });
    expect(
      container.querySelector(".cmdplinth__frame [data-testid='seal-under-test']"),
    ).not.toBeNull();
  });

  it("reserves the portrait's band before the image map arrives", () => {
    // The seal is positioned against this box. If it only appeared once
    // `/images` resolved, the life dial would drop into place a beat after the
    // rest of the panel. The art element inside it is still conditional.
    const { container } = renderZone([commander()]);
    expect(container.querySelector(".cmdplinth__frame")).not.toBeNull();
    expect(container.querySelector(".cmdplinth__art")).toBeNull();
  });
});
