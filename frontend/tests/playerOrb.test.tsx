/**
 * The player column: the life dial, and zones drawn as piles.
 *
 * Most of this is guarding hooks rather than looks. Replacing the life numeral
 * with a dial and the zone chips with piles moves two things the rest of the
 * app reaches for -- the `life-{pid}` testid that `e2e/helpers.ts` parses as a
 * number, and the click that is the only route into `ZonePeek`.
 */

import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { PlayerOrb } from "../src/components/game/PlayerOrb";
import { pileLeaves } from "../src/logic/zones";
import { useUiStore } from "../src/state/uiStore";
import { card, player } from "./fixtures";

afterEach(() => {
  cleanup();
  useUiStore.setState({ peek: null });
});

function renderOrb(overrides = {}, props = {}) {
  return render(
    <PlayerOrb
      player={player(overrides)}
      isViewer
      isActive
      hasPriority
      names={["You", "Them"]}
      {...props}
    />,
  );
}

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
