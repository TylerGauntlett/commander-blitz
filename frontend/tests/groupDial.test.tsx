/**
 * The region dial: one spoke per region that has something to land on.
 *
 * Two facts carry the whole control. The spokes are `tool:` stops inside a
 * `.wheelwrap`, which is the class `input/stops.ts` has trapped the ring inside
 * since before the dial existed -- so opening it puts the ring inside it with
 * no other wiring. And the landing is a MOMENT: the ring goes to the spoke you
 * are already in (or the first) once, on mount, and never again, because
 * `Table` re-renders on every engine push and a landing that re-ran would drag
 * the ring back under a player mid-choice. These pin both (TECH_DEBT CG-02,
 * LP-02).
 */

import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GroupDial } from "../src/components/game/GroupDial";
import { getCursor, resetCursor, setCursor } from "../src/input/cursor";
import { resetGroups } from "../src/input/groups";

/** A board with the given regions each holding one visible stop. */
function board(regions: ("hand" | "acts" | "board")[]): void {
  const sel = { hand: "hand", acts: "rail rail--right", board: "play__mine" } as const;
  const inner = { hand: "", acts: "", board: "mat__lanes" } as const;
  document.body.innerHTML = `<div class="table">${regions
    .map(
      (r) =>
        `<div class="${sel[r]}"><div class="${inner[r]}"><button data-stop="${r}:1">x</button></div></div>`,
    )
    .join("")}</div>`;
  // jsdom lays nothing out; a stop nobody can see is not a stop.
  for (const el of document.querySelectorAll<HTMLElement>("[data-stop], .table")) {
    el.getBoundingClientRect = () =>
      ({
        x: 0,
        y: 0,
        width: 100,
        height: 40,
        top: 0,
        left: 0,
        right: 100,
        bottom: 40,
      }) as DOMRect;
  }
}

beforeEach(() => {
  resetCursor();
  resetGroups();
});
afterEach(() => {
  cleanup();
  document.body.innerHTML = "";
});

describe("GroupDial", () => {
  it("draws one spoke per region that holds a landable stop, as tool stops", () => {
    board(["hand", "acts"]);
    render(<GroupDial current={null} onPick={() => undefined} />, {
      container: document.querySelector(".table") as HTMLElement,
    });
    const dial = document.querySelector("[data-testid='group-dial']");
    expect(dial?.className).toBe("wheelwrap");
    const spokes = [...document.querySelectorAll<HTMLElement>(".wheel__spoke")];
    expect(spokes.map((s) => s.dataset.stop)).toEqual(["tool:group-hand", "tool:group-acts"]);
    expect(spokes.map((s) => s.dataset.testid)).toEqual(["group-hand", "group-acts"]);
    // Choosing where to look is not a move in the game.
    expect(document.querySelectorAll(".wheel [data-action-id]").length).toBe(0);
  });

  it("lands the ring on the spoke for the region you are in", () => {
    board(["hand", "acts"]);
    render(<GroupDial current="acts" onPick={() => undefined} />, {
      container: document.querySelector(".table") as HTMLElement,
    });
    expect(getCursor()).toBe("tool:group-acts");
    expect(document.querySelector("[data-stop='tool:group-acts']")?.className).toContain(
      "wheel__spoke--here",
    );
  });

  it("lands on the first spoke when the current region is not on the dial", () => {
    board(["hand", "acts"]);
    render(<GroupDial current="board" onPick={() => undefined} />, {
      container: document.querySelector(".table") as HTMLElement,
    });
    expect(getCursor()).toBe("tool:group-hand");
  });

  it("lands once, on mount, and does not re-land when the board re-renders", () => {
    board(["hand", "acts"]);
    const { rerender } = render(<GroupDial current="hand" onPick={() => undefined} />, {
      container: document.querySelector(".table") as HTMLElement,
    });
    expect(getCursor()).toBe("tool:group-hand");
    // The player moved the ring to another spoke...
    setCursor("tool:group-acts");
    // ...and an engine push re-rendered the table underneath them.
    rerender(<GroupDial current="hand" onPick={() => undefined} />);
    rerender(<GroupDial current="hand" onPick={() => undefined} />);
    expect(getCursor()).toBe("tool:group-acts");
  });

  it("reports the pick, and only the pick", () => {
    board(["hand", "acts", "board"]);
    const onPick = vi.fn();
    render(<GroupDial current="hand" onPick={onPick} />, {
      container: document.querySelector(".table") as HTMLElement,
    });
    fireEvent.click(document.querySelector("[data-testid='group-board']") as HTMLElement);
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick).toHaveBeenCalledWith("board");
  });

  it("draws no spoke for a region that has nothing to land on", () => {
    board(["acts"]);
    render(<GroupDial current={null} onPick={() => undefined} />, {
      container: document.querySelector(".table") as HTMLElement,
    });
    expect([...document.querySelectorAll(".wheel__spoke")].map((s) => s.textContent)).toEqual([
      "Actions",
    ]);
  });
});
