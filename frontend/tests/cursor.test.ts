/**
 * The cursor store and the focus trap.
 *
 * Three behaviours are worth pinning, and each of them is a bug the design
 * round actually hit:
 *
 *   - the trap. With an overlay open, a resolver that takes the first
 *     `[data-stop]` in document order puts the ring on the board *behind* the
 *     dialog, because the board comes first in the markup. On a mouse nobody
 *     notices; on a pad the ring walks out of a modal and presses things
 *     underneath it.
 *   - the re-derive. If the element wearing `data-cursor` is replaced, the ring
 *     goes out and can never come back, because navigation starts from
 *     `[data-cursor]`.
 *   - exactly one cursor. More than one and the gate cannot say where the ring
 *     is, which is the failure `ringLost` exists to catch.
 *
 * These run in jsdom, which has no layout: every `getBoundingClientRect` is
 * zeroes. That rules out testing *navigation* here -- `tests/spatialNav.test.ts`
 * owns the scoring against synthetic rects -- and leaves this file the
 * questions that are about identity and containment rather than geometry.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { getCursor, resetCursor, resolveCursor, setCursor } from "../src/input/cursor";
import { stopElement, stopRoot, stopsIn } from "../src/input/stops";

/** jsdom gives every element a zero-sized box; `candidatesIn` drops those. */
function board(html: string): HTMLElement {
  document.body.innerHTML = `<div class="table">${html}</div>`;
  return document.querySelector(".table") as HTMLElement;
}

beforeEach(() => {
  resetCursor();
  document.body.innerHTML = "";
});

afterEach(() => {
  resetCursor();
  document.body.innerHTML = "";
});

describe("stopRoot", () => {
  it("is the table when nothing is over it", () => {
    const table = board(`<div data-stop="card:1"></div>`);
    expect(stopRoot()).toBe(table);
  });

  it("is the open dialog when one is over it", () => {
    board(`
      <div data-stop="card:1"></div>
      <div data-modal-root><button data-stop="act:a1"></button></div>
    `);
    expect(stopRoot().hasAttribute("data-modal-root")).toBe(true);
    expect(stopsIn().map((el) => el.dataset.stop)).toEqual(["act:a1"]);
  });

  it("ignores a dialog that is animating out", () => {
    /*
     * The half the prototype could not discover, because it had no
     * `AnimatePresence`. Every dialog here animates out, so an exiting one is
     * still in the DOM for its exit duration -- and without this the ring stays
     * trapped in a panel that is fading away, making `B` look broken.
     */
    board(`
      <div data-stop="card:1"></div>
      <div data-modal-root data-closing><button data-stop="act:a1"></button></div>
    `);
    expect(stopRoot().classList.contains("table")).toBe(true);
  });

  it("gives the wheel priority over a dialog under it", () => {
    board(`
      <div data-modal-root><button data-stop="act:a1"></button></div>
      <div class="wheelwrap"><button data-stop="tool:undo"></button></div>
    `);
    expect(stopsIn().map((el) => el.dataset.stop)).toEqual(["tool:undo"]);
  });
});

describe("stopElement", () => {
  it("matches an id containing selector punctuation literally", () => {
    // Action ids are opaque server strings; a colon or a dot in one would be
    // parsed as selector syntax rather than matched.
    board(`<button data-stop="act:cast.sol_ring:kicked"></button>`);
    expect(stopElement("act:cast.sol_ring:kicked")).not.toBeNull();
  });
});

describe("resolveCursor", () => {
  it("lands on the first stop when it has nowhere to go back to", () => {
    board(`<div data-stop="card:1"></div><div data-stop="card:2"></div>`);
    resolveCursor();
    expect(getCursor()).toBe("card:1");
  });

  it("stays where it is when its stop survives the rebuild", () => {
    board(`<div data-stop="card:1"></div><div data-stop="card:2"></div>`);
    setCursor("card:2");
    // A re-render that keeps the same stops.
    board(`<div data-stop="card:1"></div><div data-stop="card:2"></div>`);
    resolveCursor();
    expect(getCursor()).toBe("card:2");
  });

  it("re-derives onto a surviving stop when its own is destroyed", () => {
    /*
     * The commit-slab bug. Without this the attribute is on a detached node,
     * `navigate` finds no current stop, and the ring is stuck for the rest of
     * the game.
     */
    board(`<div data-stop="card:1"></div><div data-stop="card:2"></div>`);
    setCursor("card:2");
    board(`<div data-stop="card:1"></div>`);
    resolveCursor();
    expect(getCursor()).toBe("card:1");
    expect(document.querySelectorAll("[data-cursor]").length).toBe(1);
  });

  it("moves into a dialog the moment one opens over the board", () => {
    board(`<div data-stop="card:1"></div>`);
    setCursor("card:1");
    board(`
      <div data-stop="card:1"></div>
      <div data-modal-root><button data-stop="act:a1"></button></div>
    `);
    resolveCursor();
    expect(getCursor()).toBe("act:a1");
  });

  it("stands the ring down when there is nothing to point at", () => {
    board(`<div data-stop="card:1"></div>`);
    setCursor("card:1");
    board("");
    resolveCursor();
    expect(getCursor()).toBeNull();
    expect(document.querySelectorAll("[data-cursor]").length).toBe(0);
  });
});

describe("setCursor", () => {
  it("keeps exactly one cursor in the document", () => {
    board(`<div data-stop="card:1"></div><div data-stop="card:2"></div>`);
    setCursor("card:1");
    setCursor("card:2");
    const marked = [...document.querySelectorAll("[data-cursor]")];
    expect(marked.length).toBe(1);
    expect(marked[0].getAttribute("data-stop")).toBe("card:2");
  });

  it("refuses a stop that is not currently reachable", () => {
    // Not an error: a wheel spoke jumping the ring to a control that is not on
    // screen should decline rather than blank the ring.
    board(`<div data-stop="card:1"></div>`);
    setCursor("card:1");
    expect(setCursor("card:99")).toBe(false);
    expect(getCursor()).toBe("card:1");
  });

  it("refuses a stop hidden behind an open dialog", () => {
    board(`
      <div data-stop="card:1"></div>
      <div data-modal-root><button data-stop="act:a1"></button></div>
    `);
    expect(setCursor("card:1")).toBe(false);
  });
});
