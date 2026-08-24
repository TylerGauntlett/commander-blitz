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
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ActionPanel } from "../src/components/game/ActionPanel";
import { PromptDialog } from "../src/components/game/PromptDialog";
import { actionAttrs, candidatesIn, stopId } from "../src/input/stops";
import { chooseType } from "../src/testing/scenarios";
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
      <PromptDialog state={state} actions={actions} onAct={noop} disabled={false} />,
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
