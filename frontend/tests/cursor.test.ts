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

  it("does not take a field away from somebody typing in it", () => {
    /*
     * The pod lobby, and the bug a player would describe as "the seed box only
     * accepts one digit". `resolveCursor` runs after EVERY commit, and a
     * controlled input commits on every keystroke -- so the resolve that was
     * meant to repair a ring whose element had been replaced was instead
     * re-focusing the header's first button, one character in.
     */
    const table = document.createElement("div");
    table.className = "screen";
    table.innerHTML = `<button id="copy">Copy</button><input id="seed" aria-label="Seed" />`;
    document.body.append(table);
    resolveCursor();
    expect(getCursor()).toBe("ui:#copy");

    const seed = document.getElementById("seed") as HTMLInputElement;
    seed.focus();
    resolveCursor();

    expect(document.activeElement).toBe(seed);
    // And the ring went to the field rather than staying on a button nobody is
    // using: off the board a stop IS a focusable, so the two cannot disagree.
    expect(getCursor()).toBe("ui:#seed");
    expect(document.querySelectorAll("[data-cursor]").length).toBe(1);
    expect(seed.hasAttribute("data-cursor")).toBe(true);
  });

  it("keeps the ring on the card it is on when focus is elsewhere", () => {
    /*
     * The other half of the rule above, and the reason it is not simply "follow
     * focus". A board card is a div: it cannot hold focus, so the focused
     * element there is whatever control was last pressed. Following that would
     * drag the ring off the card the player just walked it onto, on every push
     * the engine makes.
     */
    board(`<button data-stop="tool:undo"></button><div data-stop="card:1"></div>`);
    const undo = document.querySelector("button") as HTMLButtonElement;
    undo.focus();
    setCursor("card:1");
    resolveCursor();

    expect(getCursor()).toBe("card:1");
    expect(document.activeElement).toBe(undo);
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

describe("coming back out of an overlay", () => {
  /*
   * THE BUG A PLAYER DESCRIBES AS "THE PAD DOESN'T WORK".
   *
   * Press A on a deck in the catalogue: the catalogue closes, the cursor names
   * a tile that no longer exists, and the old fallback -- "the first stop of
   * whatever is on top" -- put the ring on the first control in the pod's
   * header. Every A press that dismissed anything threw the player back to the
   * top-left of the screen, so choosing a deck and then locking in was two full
   * walks of the lobby with a wrong turn in the middle.
   */
  /*
   * ONE `.screen` ELEMENT, REWRITTEN -- not a new one each time.
   *
   * The addresses are keyed by the root ELEMENT rather than by a name, which is
   * what lets a dialog nobody told this module about be covered for free. It
   * also means a helper that blows away `document.body` between steps is
   * testing a route change rather than an overlay opening: every step would get
   * a fresh `.screen`, no address would ever match, and the test would fail for
   * a reason the app never has. React keeps one `.screen` per route mounted
   * across an overlay opening and closing, so this does too.
   */
  function screen(html: string): HTMLElement {
    let root = document.querySelector<HTMLElement>(".screen");
    if (!root) {
      root = document.createElement("div");
      root.className = "screen";
      document.body.append(root);
    }
    root.innerHTML = html;
    return root;
  }

  const POD = `<button data-testid="copy"></button><button data-testid="change-deck"></button>`;
  const CATALOG = `<div data-modal-root><button data-testid="close"></button><button data-testid="deck-a"></button></div>`;

  it("puts the ring back on the control that opened it", () => {
    screen(POD);
    resolveCursor();
    setCursor("ui:change-deck");
    expect(getCursor()).toBe("ui:change-deck");

    // The catalogue opens and lands the ring on a deck, which is what
    // `DeckCatalog` does from a layout effect.
    screen(POD + CATALOG);
    setCursor("ui:deck-a");
    expect(getCursor()).toBe("ui:deck-a");

    // Taking that deck closes it.
    screen(POD);
    resolveCursor();
    expect(getCursor()).toBe("ui:change-deck");
  });

  it("does not fall back to the first control on the screen", () => {
    // The failing shape, stated as its own assertion: `ui:copy` is `all[0]`,
    // and landing there is the whole defect rather than an incidental detail.
    screen(POD);
    resolveCursor();
    setCursor("ui:change-deck");
    screen(POD + CATALOG);
    resolveCursor();
    screen(POD);
    resolveCursor();
    expect(getCursor()).not.toBe("ui:copy");
  });

  it("backs out of a dossier onto the tile, not to the catalogue's front", () => {
    /*
     * Two overlays deep, which is why the addresses are a stack rather than one
     * slot: the dossier opens over the catalogue, and closing it must land on
     * the tile that opened it rather than at the catalogue's own first stop.
     *
     * The dossier is appended and removed rather than re-written in, for the
     * same reason `screen` keeps one root: React leaves the catalogue mounted
     * underneath, so its element has to survive the dossier opening or the
     * address keyed to it is a different element by the time we come back.
     */
    const root = screen(POD + CATALOG);
    setCursor("ui:deck-a");

    const dossier = document.createElement("div");
    dossier.setAttribute("data-modal-root", "");
    dossier.innerHTML = `<button data-testid="dossier-close"></button>`;
    root.append(dossier);
    resolveCursor();
    expect(getCursor()).toBe("ui:dossier-close");

    dossier.remove();
    resolveCursor();
    expect(getCursor()).toBe("ui:deck-a");
  });

  it("opens a NEW surface at its own front, not near where the ring was", () => {
    /*
     * THE HALF THAT MAKES THE NEAREST-STOP FALLBACK SAFE.
     *
     * A dialog opening over the board is not a stop being replaced -- it is a
     * new screen -- so measuring from where the ring stood behind it measures
     * across two things that were never on screen together. The mulligan prompt
     * is where it showed: the ring had been on a hand card at the bottom of the
     * board, so the nearest option in the new panel was whichever one happened
     * to sit lowest, and the prompt opened on Keep instead of on Mulligan for
     * reasons nothing on screen could explain.
     */
    screen(POD);
    resolveCursor();
    setCursor("ui:change-deck");
    screen(POD + CATALOG);
    resolveCursor();
    expect(getCursor()).toBe("ui:close");
  });

  it("keeps a disabled control as somewhere the ring may stand", () => {
    /*
     * Every button in the pod goes `disabled` for the round-trip of any
     * mutation. While `stopsIn` skipped disabled controls that emptied the
     * screen of stops for about 200ms, the ring had nowhere near to fall back
     * to, and it never came home. The board has always allowed this -- a
     * disabled action still carries `data-stop`, because "a decision always HAS
     * a surface" -- and the lobby was the only surface that disagreed.
     */
    screen(
      `<button data-testid="copy" disabled></button><button data-testid="deal" disabled></button>`,
    );
    expect(stopsIn().map((el) => el.dataset.testid)).toEqual(["copy", "deal"]);
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
