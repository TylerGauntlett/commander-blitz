/**
 * Stops, and the invariant they share with the action panel.
 *
 * Two rules meet here and both are load-bearing:
 *
 *   1. `ActionPanel`'s contract -- every legal action is a button carrying
 *      `data-action-id`, exactly once in the document.
 *   2. The ring's requirement -- every one of those buttons is reachable, which
 *      means every one of them also carries `data-stop="act:<id>"`.
 *
 * `actionAttrs` emits both from one call, so the two sets are equal by
 * construction. What these tests defend is that nobody goes back to writing
 * `data-action-id` by hand -- which would produce a control the mouse can press
 * and the controller cannot even see, and which no existing spec would catch.
 *
 * The duplicate check matters for a second reason the plan calls out: Playwright
 * runs in strict mode, so a duplicated `data-testid` or stop fails specs in a
 * confusing, far-away way rather than at the site of the mistake.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ActionPanel } from "../src/components/game/ActionPanel";
import { PromptDialog } from "../src/components/game/PromptDialog";
import { SchemePicker } from "../src/components/ui/SchemePicker";
import { getCursor, setCursor } from "../src/input/cursor";
import { actionAttrs, candidatesIn, stopId, stopRoot, stopsIn } from "../src/input/stops";
import { useUiStore } from "../src/state/uiStore";
import { chooseType } from "../src/testing/scenarios";
import * as scenarios from "../src/testing/scenarios";
import { action, card, gameView, pending, player } from "./fixtures";

afterEach(cleanup);

const noop = () => undefined;

function stopsAndIds(root: HTMLElement) {
  return {
    ids: [...root.querySelectorAll("[data-action-id]")].map((el) =>
      el.getAttribute("data-action-id"),
    ),
    stops: [...root.querySelectorAll("[data-stop]")].map((el) => el.getAttribute("data-stop")),
  };
}

describe("actionAttrs", () => {
  it("derives the stop from the id, so the two can never disagree", () => {
    expect(actionAttrs("a7")).toEqual({ "data-action-id": "a7", "data-stop": "act:a7" });
  });

  it("passes an opaque server id through untouched", () => {
    // Action ids are the engine's and are not ours to constrain -- they contain
    // colons, and the stop namespace has to survive that.
    const id = "cast:sol_ring:kicked";
    expect(actionAttrs(id)["data-stop"]).toBe(`act:${id}`);
  });
});

describe("stopId", () => {
  it("namespaces every surface distinctly", () => {
    expect(stopId.card(12)).toBe("card:12");
    expect(stopId.orb(2)).toBe("orb:2");
    expect(stopId.tool("mute")).toBe("tool:mute");
    expect(stopId.pile(0, "graveyard")).toBe("pile:0:graveyard");
    expect(stopId.lane(0, "Creatures")).toBe("lane:0:Creatures");
  });
});

describe("rendered surfaces", () => {
  const actions = [
    action({ id: "a1", kind: "cast", label: "Cast Bear", source_oid: 5 }),
    action({ id: "a2", kind: "activate", label: "Tap for G", source_oid: 6 }),
    action({ id: "a3", kind: "pass", label: "Pass" }),
  ];

  it("gives every action button in the panel a matching stop", () => {
    const { container } = render(
      <ActionPanel
        state={gameView()}
        actions={actions}
        onAct={noop}
        onStage={noop}
        onDeclare={noop}
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
    const { ids, stops } = stopsAndIds(container);
    expect(ids.length).toBeGreaterThan(0);
    for (const id of ids) expect(stops).toContain(`act:${id}`);
  });

  it("gives every prompt option a matching stop", () => {
    const decision = pending({
      kind: "choose_object",
      player: 0,
      prompt: "Choose a creature to sacrifice",
      options: [
        { label: "Bear", ref: { kind: "object", id: 5 }, value: 0, card: card({ oid: 5 }) },
      ],
      min_count: 1,
      max_count: 1,
    });
    const state = gameView({ pending: decision, players: [player({ pid: 0 })] });
    const { container } = render(
      <PromptDialog
        onChoose={() => undefined}
        state={state}
        actions={[action({ id: "p1", kind: "choose", choice: 0 })]}
        onAct={noop}
        disabled={false}
      />,
    );
    const { ids, stops } = stopsAndIds(container);
    expect(ids).toContain("p1");
    for (const id of ids) expect(stops).toContain(`act:${id}`);
  });

  it("keeps a wall of options reachable, as one action and many rows", () => {
    /*
     * The combobox a long decision opens with changes what is in the document
     * and must not change what is TRUE of it: one action id, wearing its
     * matching `act:` stop, and every row and control reachable by the ring.
     *
     * The rows deliberately do not carry action ids -- selecting a row is not
     * acting on it -- so the count here is 1 rather than 199, and that is the
     * assertion worth pinning: the alternative reads to every counter in the
     * app as two hundred simultaneous legal actions.
     */
    const { state, actions } = chooseType();
    const { container } = render(
      <PromptDialog
        onChoose={() => undefined}
        state={state}
        actions={actions}
        onAct={noop}
        disabled={false}
      />,
    );
    const { ids, stops } = stopsAndIds(container);

    expect(ids.length).toBe(1);
    for (const id of ids) expect(stops).toContain(`act:${id}`);
    expect(stops).toContain("combo:filter");
    expect(stops).toContain(`combo:opt:${actions[0].id}`);
    expect(stops.filter((stop) => stop?.startsWith("combo:opt:")).length).toBe(actions.length);
    expect(new Set(stops).size).toBe(stops.length);
  });

  it("never renders the same stop twice", () => {
    const { container } = render(
      <ActionPanel
        state={gameView()}
        actions={actions}
        onAct={noop}
        onStage={noop}
        onDeclare={noop}
        onUndo={noop}
        onQuit={noop}
        onToggleFullControl={noop}
        onToggleManualMana={noop}
        narrating={true}
        onSkipNarration={noop}
        busy={false}
        aiThinking={false}
        standDown={false}
      />,
    );
    const { stops } = stopsAndIds(container);
    expect(new Set(stops).size).toBe(stops.length);
  });

  it("gives the whole combat bar stops, marks and slab included", () => {
    /*
     * THE BUG THIS EXISTS FOR. The combat dock is three controls and only one
     * of them -- "No attacks" -- is a server action, so only that one picked up
     * a stop from `actionAttrs`. The other two are local staging: "All attack"
     * writes every attacker into `uiStore`, the slab declares what is staged.
     * Neither carried `data-stop`, which made the two most-pressed buttons of a
     * combat step reachable by mouse and by nothing else -- no arrow key, no
     * d-pad, and no `L2`, which lands in this dock precisely so a handheld
     * player does not have to walk there.
     *
     * The panel's own id invariant could not catch it: they carry no
     * `data-action-id`, so every count of the action space was correct while
     * the controller could not press either one.
     */
    const { state, actions } = scenarios.combatDeclareAttackers();
    const { container } = render(
      <ActionPanel
        state={state}
        actions={actions}
        onAct={noop}
        onStage={noop}
        onDeclare={noop}
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

    // Asserted through the controls rather than through the stop list, because
    // the claim is about these three buttons specifically -- a stop that moved
    // to some other node would still be "contained" by a list.
    expect(screen.getByTestId("combat-all").dataset.stop).toBe("commit:all");
    expect(screen.getByTestId("combat-confirm").dataset.stop).toBe("commit");
    expect(screen.getByTestId("combat-skip").dataset.stop).toMatch(/^act:/);

    /*
     * ...and in that order in the document, which is also left-to-right on
     * screen. `L2` lands on the first stop of the dock and one press of right
     * walks to the next, so the row's order IS the navigation, and a control
     * inserted ahead of the mark would silently steal the landing.
     */
    const dock = container.querySelector(".commit-dock") as HTMLElement;
    expect(
      [...dock.querySelectorAll("[data-stop]")].map((el) => el.getAttribute("data-stop"))[0],
    ).toBe("commit:all");

    const { stops } = stopsAndIds(container);
    expect(new Set(stops).size).toBe(stops.length);
  });

  it("gives the tool strip stops, so the ring can reach the settings", () => {
    const { container } = render(
      <ActionPanel
        state={gameView()}
        actions={actions}
        onAct={noop}
        onStage={noop}
        onDeclare={noop}
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
    const { stops } = stopsAndIds(container);
    for (const tool of ["settings", "full-control", "manual-mana"]) {
      expect(stops).toContain(`tool:${tool}`);
    }

    /*
     * ...and the three inside the menu, once it is open.
     *
     * They used to be three permanent buttons in the strip. They are the same
     * three controls with the same stop ids -- the ring reaches them exactly as
     * it did -- but only while the menu holding them is open, which is what
     * this half is here to hold. A rewrite that quietly dropped one would
     * otherwise pass, because the strip it left is still full of stops.
     */
    for (const tool of ["mute", "undo", "quit"]) {
      expect(stops).not.toContain(`tool:${tool}`);
    }
    fireEvent.click(screen.getByTestId("settings"));
    const opened = stopsAndIds(container).stops;
    for (const tool of ["mute", "undo", "quit"]) {
      expect(opened).toContain(`tool:${tool}`);
    }
  });

  /*
   * TECH_DEBT FB-12: the open menu is a modal, for the ring as for the mouse.
   *
   * Each assertion is one of the four ways it used to fail a pad player: the
   * ring could walk out of it, opening it left the ring on the gear, the
   * control-scheme picker inside it had no stops, and closing it from `B`
   * (which is `Table`'s, so here it is the store flag `Table.back` clears)
   * left the ring on a node that no longer existed.
   */
  it("traps the ring in the open settings menu and gives it back on close", () => {
    useUiStore.setState({ settingsOpen: false });
    setCursor(null);
    const { container } = render(
      <ActionPanel
        state={gameView()}
        actions={actions}
        onAct={noop}
        onStage={noop}
        onDeclare={noop}
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
    expect(setCursor(stopId.tool("settings"))).toBe(true);
    fireEvent.click(screen.getByTestId("settings"));

    const menu = screen.getByTestId("settings-menu");
    // The trap: whatever is on top owns the ring, and the menu is on top.
    expect(menu.hasAttribute("data-modal-root")).toBe(true);
    expect(stopRoot()).toBe(menu);
    // ...so the board's stops are not stops while it is up, and the strip's
    // other two tools are not either.
    const inside = stopsIn(stopRoot()).map((el) => el.dataset.stop);
    expect(inside).not.toContain(stopId.tool("full-control"));
    expect(inside).not.toContain(stopId.tool("settings"));
    // The scheme picker is reachable now, and in the menu's own namespace.
    for (const scheme of ["auto", "pad", "keyboard", "mouse"]) {
      expect(inside).toContain(stopId.tool(`scheme-${scheme}`));
    }
    // Opening it moved the ring in.
    expect(getCursor()).toBe(stopId.tool("mute"));

    // `B` is `Table.back`, which clears the store flag. The ring comes home.
    act(() => useUiStore.getState().setSettingsOpen(false));
    expect(container.querySelector('[data-testid="settings-menu"]')).toBeNull();
    expect(getCursor()).toBe(stopId.tool("settings"));

    // A press elsewhere closes it too -- but that is a mouse player going
    // somewhere, and the ring is not dragged back to the gear behind them.
    fireEvent.click(screen.getByTestId("settings"));
    expect(getCursor()).toBe(stopId.tool("mute"));
    setCursor(stopId.tool("undo"));
    fireEvent.pointerDown(document.body);
    expect(container.querySelector('[data-testid="settings-menu"]')).toBeNull();
    expect(getCursor()).not.toBe(stopId.tool("settings"));
  });

  it("leaves the front door's scheme picker on the focusable fallback", () => {
    // One declared stop on a surface switches the fallback off for every other
    // control on it, so the picker only declares when its host asks.
    render(<SchemePicker />);
    for (const scheme of ["auto", "pad", "keyboard", "mouse"]) {
      expect(screen.getByTestId(`scheme-${scheme}`).hasAttribute("data-stop")).toBe(false);
    }
  });
});

/*
 * jsdom has no layout, so every box here is stated rather than measured. That
 * is the point: the question is what `candidatesIn` does with a given set of
 * boxes, and a real browser would only make the boxes harder to control.
 */
function boxed(el: Element, x: number, y: number, w: number, h: number): void {
  const rect = {
    x,
    y,
    width: w,
    height: h,
    top: y,
    left: x,
    right: x + w,
    bottom: y + h,
    toJSON() {
      return this;
    },
  } as DOMRect;
  el.getBoundingClientRect = () => rect;
}

describe("candidatesIn", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  function table(html: string): HTMLElement {
    document.body.innerHTML = `<div class="table">${html}</div>`;
    const root = document.querySelector(".table") as HTMLElement;
    boxed(root, 0, 0, 1280, 800);
    return root;
  }

  it("keeps a stop with a box inside its ancestors", () => {
    const root = table(`<div class="lane"><button data-stop="card:1"></button></div>`);
    boxed(root.querySelector(".lane") as Element, 0, 0, 600, 200);
    boxed(root.querySelector("[data-stop]") as Element, 10, 10, 120, 168);

    expect(candidatesIn(root).map((c) => c.id)).toEqual(["card:1"]);
  });

  it("drops a stop an ancestor has clipped to nothing", () => {
    /*
     * THE BUG THIS EXISTS FOR. An opponent's lanes are `height: 0;
     * overflow: hidden` so their cards stay in the document for `FxLayer` to
     * anchor to -- and a clipped card still reports its own full box, so a
     * zero-size check alone let the ring walk onto a card nobody can see.
     *
     * Worse, `handheldAssert`'s `unreachable` calls this same function, so the
     * gate agreed the board was fine.
     */
    const root = table(`<div class="mat__lanes"><button data-stop="card:1"></button></div>`);
    const lanes = root.querySelector(".mat__lanes") as HTMLElement;
    lanes.style.overflow = "hidden";
    boxed(lanes, 0, 0, 600, 0);
    boxed(root.querySelector("[data-stop]") as Element, 10, 10, 120, 168);

    expect(candidatesIn(root)).toEqual([]);
  });

  it("drops a stop scrolled out of a clipping ancestor", () => {
    // Same rule, the other way a box leaves its parent: the card is a real
    // size in a real box, and simply not within it.
    const root = table(`<div class="acts__list"><button data-stop="act:a9"></button></div>`);
    const list = root.querySelector(".acts__list") as HTMLElement;
    list.style.overflowY = "auto";
    boxed(list, 0, 100, 240, 300);
    boxed(root.querySelector("[data-stop]") as Element, 0, 460, 240, 44);

    expect(candidatesIn(root)).toEqual([]);
  });

  it("does not treat a visible overflow as a clip", () => {
    /*
     * A zero-height parent that does NOT clip is how the hand's lift works --
     * the raised card overhangs its slot on purpose. Filtering on the parent's
     * size alone would have deleted the hand.
     */
    const root = table(`<div class="hand__rail"><button data-stop="card:4"></button></div>`);
    boxed(root.querySelector(".hand__rail") as Element, 0, 0, 900, 0);
    boxed(root.querySelector("[data-stop]") as Element, 10, -80, 120, 168);

    expect(candidatesIn(root).map((c) => c.id)).toEqual(["card:4"]);
  });

  it("still drops a stop with no box of its own", () => {
    // The original rule, unchanged: a card mid-exit reports an empty box and
    // navigating onto one puts the ring nowhere.
    const root = table(`<button data-stop="card:1"></button>`);
    boxed(root.querySelector("[data-stop]") as Element, 0, 0, 0, 0);

    expect(candidatesIn(root)).toEqual([]);
  });
});

describe("the source tree", () => {
  const SRC = join(__dirname, "..", "src");

  function sources(dir: string): string[] {
    return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) return sources(path);
      return /\.tsx$/.test(entry.name) ? [path] : [];
    });
  }

  it("writes no bare data-action-id, so the stop can never be forgotten", () => {
    /*
     * `actionAttrs` is the only way to emit one. A hand-written attribute would
     * produce a control a mouse can press and a controller cannot reach -- and
     * every existing spec would still pass, because they all click.
     */
    const offenders = sources(SRC)
      .filter((path) => !path.includes(".stories."))
      .filter((path) => /\sdata-action-id=/.test(readFileSync(path, "utf8")));
    expect(offenders).toEqual([]);
  });
});
