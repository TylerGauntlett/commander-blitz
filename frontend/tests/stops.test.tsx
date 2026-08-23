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
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ActionPanel } from "../src/components/game/ActionPanel";
import { PromptDialog } from "../src/components/game/PromptDialog";
import { actionAttrs, stopId } from "../src/input/stops";
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
    for (const tool of ["mute", "full-control", "manual-mana", "undo", "quit"]) {
      expect(stops).toContain(`tool:${tool}`);
    }
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
