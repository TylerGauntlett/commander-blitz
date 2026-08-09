/**
 * The player column: the commander plinth, the life dial, and zones as piles.
 *
 * Most of this is guarding hooks rather than looks. Replacing the life numeral
 * with a dial and the zone chips with piles moves two things the rest of the
 * app reaches for -- the `life-{pid}` testid that `e2e/helpers.ts` parses as a
 * number, and the click that is the only route into `ZonePeek`.
 *
 * The plinth cases guard the thing that is easy to lose in a re-skin: its state
 * is meant to be legible on three channels, and two of them (the word and the
 * glyph) are asserted here because a screenshot cannot fail a build.
 */

import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { GameView, PlayerView } from "../src/api/types";
import { PlayerOrb } from "../src/components/game/PlayerOrb";
import { pileLeaves } from "../src/logic/zones";
import { useUiStore } from "../src/state/uiStore";
import { card, gameView, player } from "./fixtures";

afterEach(() => {
  cleanup();
  useUiStore.setState({ peek: null });
});

function renderOrb(
  overrides: Partial<PlayerView> = {},
  props = {},
  view: Partial<GameView> = {},
) {
  const seat = player(overrides);
  // `commandersOf` reads `state.players[pid]`, so the seat under test has to sit
  // at its own index -- an orb rendered for pid 2 against a two-player view
  // would look up undefined.
  const players = Array.from({ length: seat.pid + 1 }, (_, pid) =>
    pid === seat.pid ? seat : player({ pid }),
  );
  return render(
    <PlayerOrb
      state={gameView({ players, seat: seat.pid, ...view })}
      player={seat}
      isViewer
      isActive
      hasPriority
      names={["You", "Them"]}
      {...props}
    />,
  );
}

/** A commander sitting in the command zone, ready to be found by the plinth. */
function commander(overrides = {}) {
  return card({
    oid: 99,
    name: "Aesi, Tyrant of Gyre Strait",
    mana_cost: "{4}{G}{U}",
    is_commander: true,
    zone: "command",
    ...overrides,
  });
}

describe("the commander plinth", () => {
  it("puts the commander in the info panel rather than in a corner", () => {
    const { container, getByTestId } = renderOrb({ command: [commander()] });
    expect(container.querySelector(".orb .cmdzone")).not.toBeNull();
    expect(getByTestId("commander-99")).not.toBeNull();
  });

  it("shows the commander's name in full rather than a count", () => {
    // The whole reason it stopped being a shrunken card face: at ~74px the name
    // clipped to "Aesi, Tyra…" -- docs/mockup-fidelity.md defect #5.
    const { container } = renderOrb({ command: [commander()] });
    expect(container.querySelector(".cmdplinth__name")?.textContent).toBe(
      "Aesi, Tyrant of Gyre Strait",
    );
  });

  it("costs nothing at all when no commander is anywhere visible", () => {
    const { container } = renderOrb({ command: [] });
    expect(container.querySelector(".cmdzone")).toBeNull();
  });

  const STATES: [string, string, Partial<PlayerView>, Partial<GameView>, boolean][] = [
    ["waiting", "In command", { command: [commander()] }, {}, false],
    [
      "deployed",
      "On the battlefield",
      { command: [] },
      { battlefield: [commander({ zone: "battlefield" })] },
      false,
    ],
    [
      "fallen",
      "In the graveyard",
      { command: [], graveyard: [commander({ zone: "graveyard" })] },
      {},
      false,
    ],
    ["fallen", "Exiled", { command: [], exile: [commander({ zone: "exile" })] }, {}, false],
    ["ready", "Ready", { command: [commander()] }, {}, true],
  ];

  it.each(STATES)(
    "says %s in words as well as in colour",
    (key, word, seat, view, castable) => {
      // The word channel, and the glyph beside it. They exist so the state is
      // legible at orb size, which the green rim, on its own, never was.
      const { getByTestId } = renderOrb(
        seat,
        // A castable commander is one the *server* named in a legal action. The
        // client never works it out from mana.
        { playableOids: castable ? new Set([99]) : new Set() },
        view,
      );
      const slot = getByTestId("commander-99");
      expect(slot.getAttribute("data-cmd-state")).toBe(key);
      expect(slot.querySelector(".cmdplinth__word")?.textContent).toBe(word);
      expect(slot.querySelector(".cmdplinth__glyph")?.textContent ?? "").not.toBe("");
    },
  );

  it("only lets you click a commander the server says you can cast", () => {
    const waiting = renderOrb({ command: [commander()] });
    expect((waiting.getByTestId("commander-99") as HTMLButtonElement).disabled).toBe(true);

    cleanup();
    const ready = renderOrb({ command: [commander()] }, { playableOids: new Set([99]) });
    expect((ready.getByTestId("commander-99") as HTMLButtonElement).disabled).toBe(false);
  });

  it("casts through the caller's play path rather than an action id", () => {
    // A gesture surface like the hand: giving it a `data-action-id` would put
    // two buttons on one action. e2e/cycle3.spec.ts guards the same invariant.
    const cast: number[] = [];
    const { getByTestId } = renderOrb(
      { command: [commander()] },
      {
        playableOids: new Set([99]),
        onCastCommander: (c: { oid: number }) => cast.push(c.oid),
      },
    );
    const slot = getByTestId("commander-99");
    expect(slot.querySelector("[data-action-id]")).toBeNull();
    expect(slot.getAttribute("data-action-id")).toBeNull();
    fireEvent.click(slot);
    expect(cast).toEqual([99]);
  });

  it("shows the tax beside the cost it modifies, not the cast count", () => {
    // `commander_cost` is the generic already doubled by the engine;
    // `commander_tax` counts prior casts. Showing the latter would say "+2"
    // when the player owes four.
    const { getByTestId } = renderOrb({
      command: [commander()],
      commander_tax: { "99": 2 },
      commander_cost: { "99": 4 },
    });
    expect(getByTestId("commander-99").querySelector(".cmdslot__tax")?.textContent).toBe("+4");
  });

  it("drops the cost row once the commander has left the command zone", () => {
    // A mana cost is only information where you could pay it.
    const { getByTestId } = renderOrb({
      command: [],
      graveyard: [commander({ zone: "graveyard" })],
    });
    expect(getByTestId("commander-99").querySelector(".cmdplinth__cost")).toBeNull();
  });
});

describe("the life dial", () => {
  it("keeps the life testid holding a bare number", () => {
    // `lifeOf()` in e2e/helpers.ts does `Number(textContent)` on this node.
    // Any extra character in it breaks every spec that reads a life total.
    const { getByTestId } = renderOrb({ pid: 0, life: 37 });
    const node = getByTestId("life-0");
    expect(node.textContent).toBe("37");
    expect(Number(node.textContent)).toBe(37);
  });

  it("puts the number inside the dial rather than replacing it", () => {
    const { container } = renderOrb({ life: 40 });
    expect(container.querySelector(".dial .dial__n")).not.toBeNull();
  });

  it("marks an opponent's dial differently from the viewer's", () => {
    // Desaturated copper: legible, but plainly reference material rather than
    // the number you are managing.
    const { container } = renderOrb({}, { isViewer: false });
    expect(container.querySelector(".dial--foe")).not.toBeNull();
    expect(container.querySelector(".dial--mine")).toBeNull();
  });

  it("marks whose turn it is on the dial", () => {
    const { container } = renderOrb({}, { isActive: true });
    expect(container.querySelector(".dial--active")).not.toBeNull();
  });

  it("shows OUT rather than a number for a dead player", () => {
    const { getByTestId } = renderOrb({ pid: 1, has_lost: true, loss_reason: "life" });
    expect(getByTestId("life-1").textContent).toBe("OUT");
  });

  it("keeps the data-player anchor the arrows and effects use", () => {
    const { container } = renderOrb({ pid: 2 });
    expect(container.querySelector('[data-player="2"]')).not.toBeNull();
  });
});

describe("the zone piles", () => {
  it("draws one pile per zone that has somewhere to go", () => {
    const { container } = renderOrb({ exile: [card()] });
    const testids = [...container.querySelectorAll(".pile")].map((n) =>
      n.getAttribute("data-testid"),
    );
    expect(testids).toEqual([
      "pile-0-library",
      "pile-0-hand",
      "pile-0-graveyard",
      "pile-0-exile",
      "pile-0-command",
    ]);
  });

  it("hides the exile pile when nothing is exiled", () => {
    const { container } = renderOrb({ exile: [] });
    expect(container.querySelector('[data-testid="pile-0-exile"]')).toBeNull();
  });

  it("puts the exact count on the top leaf", () => {
    // The leaf count is capped; the number never is.
    const { container } = renderOrb({ library_count: 200 });
    const pile = container.querySelector('[data-testid="pile-0-library"]');
    expect(pile?.querySelector(".pile__leaf--top")?.textContent).toBe("200");
  });

  it("draws as many leaves as the arithmetic says", () => {
    const { container } = renderOrb({ library_count: 37 });
    const pile = container.querySelector('[data-testid="pile-0-library"]');
    // Body leaves only -- the top leaf carries the number and is not one.
    const leaves = pile?.querySelectorAll(".pile__leaf:not(.pile__leaf--top)").length;
    expect(leaves).toBe(pileLeaves(37));
  });

  it("opens the zone viewer when clicked", () => {
    // The load-bearing one. These replaced the chips, and the chips were how
    // the graveyard was reachable at all.
    const { getByTestId } = renderOrb({ graveyard: [card()] });
    fireEvent.click(getByTestId("pile-0-graveyard"));
    expect(useUiStore.getState().peek).toEqual({ pid: 0, zone: "graveyard" });
  });

  it("opens the command zone too", () => {
    const { getByTestId } = renderOrb({ command: [card()] });
    fireEvent.click(getByTestId("pile-0-command"));
    expect(useUiStore.getState().peek).toEqual({ pid: 0, zone: "command" });
  });

  it("does not pretend the library can be opened", () => {
    // Hidden information: a control that does nothing when clicked is worse
    // than no control.
    const { getByTestId } = renderOrb();
    const library = getByTestId("pile-0-library");
    expect(library.tagName).toBe("DIV");
    fireEvent.click(library);
    expect(useUiStore.getState().peek).toBeNull();
  });

  it("marks an empty zone so it reads as empty rather than tiny", () => {
    const { getByTestId } = renderOrb({ graveyard: [] });
    expect(getByTestId("pile-0-graveyard").className).toContain("pile--empty");
  });
});

describe("what the piles did not replace", () => {
  it("still renders the mana row with its spent markings", () => {
    // Neither mockup has this, and it is driven by the engine's own solved
    // payment -- losing it in a re-skin would be silent.
    const { container } = renderOrb({
      mana: {
        pool: {},
        total: 2,
        sources: [
          { oid: 5, options: [["G"]], symbols: ["G"], amount: 1 },
          // An ambiguous source is one split pip, not two solid ones -- two
          // would claim a mana that does not exist.
          { oid: 6, options: [["G"], ["U"]], symbols: ["G", "U"], amount: 1 },
        ],
      },
    });
    const row = container.querySelector('[data-testid="mana-0"]');
    expect(row).not.toBeNull();
    expect(row?.querySelectorAll(".mana-pip").length).toBe(2);
  });

  it("hides the mana row entirely when there is none", () => {
    const { container } = renderOrb({ mana: { sources: [], pool: {}, total: 0 } });
    expect(container.querySelector('[data-testid="mana-0"]')).toBeNull();
  });
});
