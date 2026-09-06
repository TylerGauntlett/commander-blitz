/**
 * The board's regions, and the trap that keeps the ring inside one.
 *
 * jsdom has no layout, so every box here is stated rather than measured -- and
 * that is what these tests are for. The interesting cases are all about boxes:
 * a region whose container is missing, one whose stops are clipped to nothing,
 * and the modal trap winning over the group trap.
 *
 * `tests/spatialNav.test.ts` owns the scoring against synthetic rects and
 * `tests/cursor.test.ts` owns identity and containment; this file owns which
 * BOX the ring is allowed to move inside.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  GROUPS,
  getGroup,
  groupOf,
  groupRoot,
  groupsPresent,
  landableStopsIn,
  nextGroup,
  rememberStop,
  rememberedStop,
  resetGroups,
  setGroup,
  subscribeGroup,
} from "../src/input/groups";
import { activeRoot, candidatesIn, escapeGroup, sendableIn } from "../src/input/stops";

/** jsdom reports a zero box for everything; a stop needs one to count. */
function boxed(el: Element, w = 100, h = 40): void {
  el.getBoundingClientRect = () =>
    ({
      x: 0,
      y: 0,
      width: w,
      height: h,
      top: 0,
      left: 0,
      right: w,
      bottom: h,
      toJSON() {
        return this;
      },
    }) as DOMRect;
}

/** A board with a stop in each named region. */
function board(regions: string[] = ["hand", "acts", "seats", "orb", "board"]): void {
  const html: Record<string, string> = {
    hand: '<div class="hand"><button data-stop="card:1"></button></div>',
    acts: '<aside class="rail rail--right"><button data-stop="act:a1"></button></aside>',
    seats: '<div class="play__opponents"><button data-stop="orb:1"></button></div>',
    orb: '<div class="play__mine"><div class="mat__side"><button data-stop="orb:0"></button></div></div>',
    board:
      '<div class="play__mine"><div class="mat__lanes"><button data-stop="card:9"></button></div></div>',
  };
  document.body.innerHTML = `<div class="table">${regions.map((r) => html[r]).join("")}</div>`;
  boxed(document.querySelector(".table") as Element, 1280, 800);
  for (const el of document.querySelectorAll("[data-stop]")) boxed(el);
}

beforeEach(() => {
  resetGroups();
  document.body.innerHTML = "";
  document.documentElement.removeAttribute("data-input");
});

afterEach(() => {
  resetGroups();
  document.body.innerHTML = "";
  document.documentElement.removeAttribute("data-input");
});

describe("groupsPresent", () => {
  it("lists the regions that are on screen with something in them", () => {
    board(["hand", "acts"]);
    expect(groupsPresent()).toEqual(["hand", "acts"]);
  });

  it("skips a region whose container is not rendered", () => {
    board(["hand"]);
    expect(groupsPresent()).toEqual(["hand"]);
  });

  it("skips a region that is there and empty", () => {
    /*
     * An empty hand you can still cycle into takes the ring somewhere with
     * nothing to land on -- and the ring going out is the failure `ringLost`
     * exists to catch, arriving by a route the player asked for.
     */
    document.body.innerHTML = `<div class="table">
      <div class="hand"></div>
      <aside class="rail rail--right"><button data-stop="act:a1"></button></aside>
    </div>`;
    boxed(document.querySelector(".table") as Element, 1280, 800);
    boxed(document.querySelector("[data-stop]") as Element);

    expect(groupsPresent()).toEqual(["acts"]);
  });

  it("skips a region whose stops an ancestor has clipped away", () => {
    /*
     * The handheld case, and the reason the check is on visibility rather than
     * on presence: an opponent's lanes are `height: 0; overflow: hidden` so
     * their cards stay in the document for `FxLayer` to anchor to, and a
     * clipped card still reports its own full box.
     */
    document.body.innerHTML = `<div class="table">
      <div class="play__mine"><div class="mat__lanes"><button data-stop="card:9"></button></div></div>
    </div>`;
    boxed(document.querySelector(".table") as Element, 1280, 800);
    const lanes = document.querySelector(".mat__lanes") as HTMLElement;
    lanes.style.overflow = "hidden";
    boxed(lanes, 600, 0);
    boxed(document.querySelector("[data-stop]") as Element, 120, 168);

    expect(groupsPresent()).toEqual([]);
  });
});

describe("landableStopsIn", () => {
  /*
   * The rule that had two definitions.
   *
   * `groupsPresent` filtered by visibility -- an empty hand must not be a
   * destination -- while ENTERING a region took the first `[data-stop]` in
   * document order. On a handheld an opponent's cards are clipped to zero
   * height and still in the document, so "this region has something visible"
   * and "the first thing in it is visible" are different questions, and only
   * the first was being asked. The ring could therefore be sent to a card
   * nobody could see, in a region that was correctly offered.
   */
  it("skips the stops an ancestor has clipped away", () => {
    document.body.innerHTML = `<div class="table"><div class="hand">
      <div class="clipped"><button data-stop="card:1"></button></div>
      <button data-stop="card:2"></button>
    </div></div>`;
    boxed(document.querySelector(".table") as Element, 1280, 800);
    const clipped = document.querySelector(".clipped") as HTMLElement;
    clipped.style.overflow = "hidden";
    boxed(clipped, 200, 0);
    for (const el of document.querySelectorAll("[data-stop]")) boxed(el);

    const hand = document.querySelector(".hand") as HTMLElement;
    expect(landableStopsIn(hand).map((el) => el.dataset.stop)).toEqual(["card:2"]);
  });

  it("keeps document order among the ones that are visible", () => {
    // Entering a region lands on the first landable stop, so the order is part
    // of the contract rather than an accident of the filter.
    board(["hand"]);
    const hand = document.querySelector(".hand") as HTMLElement;
    expect(landableStopsIn(hand).map((el) => el.dataset.stop)).toEqual(["card:1"]);
  });

  /*
   * A dialog fading out still holds its buttons. `stopRoot` stops treating it
   * as the surface on top the moment `data-closing` appears, but its stops
   * stayed in every list for the length of the fade -- so a cursor left on one
   * was still "found", the return address beneath was consumed unapplied, and
   * when the dialog finally left the ring fell to the nearest stop: a creature
   * in the middle of the board, at a block decision it could not answer.
   */
  it("leaves out the stops of a surface that is closing, for landing and for the cursor", () => {
    document.body.innerHTML = `<div class="table">
      <div class="acts"><button data-stop="act:a1"></button></div>
      <div data-modal-root data-closing><button data-stop="act:a0-choose"></button></div>
    </div>`;
    const table = document.querySelector(".table") as HTMLElement;
    boxed(table, 1280, 800);
    for (const el of document.querySelectorAll("[data-stop]")) boxed(el);

    expect(landableStopsIn(table).map((el) => el.dataset.stop)).toEqual(["act:a1"]);
    expect(candidatesIn(table).map((c) => c.id)).toEqual(["act:a1"]);
  });
});

describe("nextGroup", () => {
  it("steps forwards and wraps", () => {
    board(["hand", "acts", "seats"]);
    expect(nextGroup("hand", 1)).toBe("acts");
    expect(nextGroup("seats", 1)).toBe("hand");
  });

  it("steps backwards and wraps", () => {
    board(["hand", "acts", "seats"]);
    expect(nextGroup("hand", -1)).toBe("seats");
  });

  it("skips over a region that is not there", () => {
    // `acts` is missing, so `hand` -> `seats` in one press rather than a press
    // that appears to do nothing.
    board(["hand", "seats"]);
    expect(nextGroup("hand", 1)).toBe("seats");
  });

  it("lands somewhere on the very first press", () => {
    // From nowhere, forwards is the first region and backwards is the last, so
    // the first press is never a no-op.
    board(["hand", "acts"]);
    expect(nextGroup(null, 1)).toBe("hand");
    expect(nextGroup(null, -1)).toBe("acts");
  });

  it("returns null when there is no board to step around", () => {
    document.body.innerHTML = "";
    expect(nextGroup(null, 1)).toBeNull();
  });

  it("recovers when the region it was in has gone", () => {
    // Your hand can empty while you are in it. Falling back to the first
    // present region beats returning null, which would read as a dead button.
    board(["acts", "seats"]);
    expect(nextGroup("hand", 1)).toBe("acts");
  });
});

describe("the current region", () => {
  it("stamps `data-group` so the stylesheet can dim the rest", () => {
    // A trap you cannot see is a wall you cannot explain: without a mark,
    // pressing a direction into the edge of a region simply does nothing.
    setGroup("acts");
    expect(document.documentElement.getAttribute("data-group")).toBe("acts");

    setGroup(null);
    expect(document.documentElement.hasAttribute("data-group")).toBe(false);
  });

  it("notifies subscribers, and only on a change", () => {
    let calls = 0;
    const off = subscribeGroup(() => {
      calls += 1;
    });

    setGroup("hand");
    setGroup("hand");
    setGroup("orb");
    off();
    setGroup("board");

    expect(calls).toBe(2);
    expect(getGroup()).toBe("board");
  });

  it("remembers where the ring was, per region", () => {
    // Coming back to the hand and landing on the card you were reading is the
    // difference between a jump and a reset.
    rememberStop("hand", "card:7");
    expect(rememberedStop("hand")).toBe("card:7");
    expect(rememberedStop("acts")).toBeUndefined();
  });

  it("forgets everything on reset, so a new game starts clean", () => {
    setGroup("hand");
    rememberStop("hand", "card:7");
    resetGroups();

    expect(getGroup()).toBeNull();
    expect(rememberedStop("hand")).toBeUndefined();
  });
});

describe("groupOf and groupRoot", () => {
  it("finds the region an element is in", () => {
    board();
    const handCard = document.querySelector(".hand [data-stop]") as HTMLElement;
    expect(groupOf(handCard)).toBe("hand");
  });

  it("returns null for something in none of them", () => {
    board();
    const outside = document.createElement("div");
    document.body.append(outside);
    expect(groupOf(outside)).toBeNull();
  });

  it("resolves every declared region to a container", () => {
    // A selector that stops matching is the silent way this breaks: the region
    // simply drops out of the cycle and nobody notices which one.
    board();
    for (const group of GROUPS) {
      expect(groupRoot(group.id), group.id).not.toBeNull();
    }
  });
});

describe("activeRoot", () => {
  it("is the whole board before any region has been entered", () => {
    // Exactly how the ring behaved before regions existed.
    board();
    document.documentElement.setAttribute("data-input", "pad");
    expect(activeRoot()).toBe(document.querySelector(".table"));
  });

  it("is the region once one is entered", () => {
    board();
    document.documentElement.setAttribute("data-input", "pad");
    setGroup("hand");
    expect(activeRoot()).toBe(document.querySelector(".hand"));
  });

  it("is the whole board for a mouse, whatever region is set", () => {
    /*
     * A mouse player has no ring at all, and a desktop keyboard user expects
     * Tab-like freedom. Trapping either inside a region is a behaviour
     * regression nobody asked for.
     */
    board();
    document.documentElement.setAttribute("data-input", "mouse");
    setGroup("hand");
    expect(activeRoot()).toBe(document.querySelector(".table"));
  });

  it("gives way to an open dialog", () => {
    /*
     * THE MODAL TRAP ALWAYS WINS. A group trap under an open prompt would let a
     * direction press reach the board behind it -- which is the whole failure
     * `stopRoot` exists for, arriving through a door it was not watching.
     */
    board();
    document.documentElement.setAttribute("data-input", "pad");
    setGroup("hand");
    const dialog = document.createElement("div");
    dialog.setAttribute("data-modal-root", "");
    dialog.innerHTML = '<button data-stop="act:a9"></button>';
    document.querySelector(".table")?.append(dialog);

    expect(activeRoot()).toBe(dialog);
  });

  it("gives way to the region dial above everything", () => {
    // `.wheelwrap` is first in `stopRoot`'s order and has been since it was
    // written -- the dial is the thing it was named for.
    board();
    document.documentElement.setAttribute("data-input", "pad");
    setGroup("hand");
    const wheel = document.createElement("div");
    wheel.className = "wheelwrap";
    document.querySelector(".table")?.append(wheel);

    expect(activeRoot()).toBe(wheel);
  });

  it("falls back to the board when the region has gone", () => {
    // The hand can empty while the ring is in it. A trap resolving to nothing
    // would leave every direction a wall.
    board(["acts"]);
    document.documentElement.setAttribute("data-input", "pad");
    setGroup("hand");
    expect(activeRoot()).toBe(document.querySelector(".table"));
  });
});

/**
 * The soft half of the region trap.
 *
 * THE TRAP WAS A ONE-WAY DOOR ON A STEAM DECK, and that is the case these
 * exist for. In gaming mode Steam hands the browser a KEYBOARD rather than a
 * gamepad, so `L1`/`R1`/`L2` -- the only three exits a region had -- emit
 * nothing. A region is entered automatically by `Table`'s cursor reconciler, so
 * the first direction press of the game locked the ring in one region for the
 * rest of it and the pad appeared to die halfway down the screen.
 *
 * The rule now is the one a console scroll pane uses: a direction with somewhere
 * to go inside the region is the region's, and a direction with nowhere to go
 * leaves it. The two things worth pinning are that it lets you out of a REGION,
 * and that it does not let you out of a MODAL.
 */
describe("escapeGroup", () => {
  /** Stack the regions vertically so "up" and "down" mean something. */
  function stacked(): void {
    board(["hand", "acts"]);
    const at = (el: Element, top: number, height: number, left = 0, width = 200) => {
      el.getBoundingClientRect = () =>
        ({
          x: left,
          y: top,
          width,
          height,
          top,
          left,
          right: left + width,
          bottom: top + height,
          toJSON() {
            return this;
          },
        }) as DOMRect;
    };
    at(document.querySelector(".table") as Element, 0, 800, 0, 1280);
    // The hand at the bottom, the action rail above it, as on the real board.
    at(document.querySelector('[data-stop="card:1"]') as Element, 600, 100);
    at(document.querySelector('[data-stop="act:a1"]') as Element, 200, 100);
    document.documentElement.setAttribute("data-input", "pad");
  }

  it("leaves the region when the region has nowhere left to go", () => {
    stacked();
    setGroup("hand");
    // The hand holds one stop, so "up" inside it is a wall -- and that wall is
    // the region's edge rather than the board's.
    expect(escapeGroup("card:1", "up")).toBe("act:a1");
  });

  it("refuses when no region is trapping the ring", () => {
    /*
     * A wall on the open board is a REAL wall, and softening it would mean the
     * ring never reports one -- which is what draws the nudge, plays the deny
     * voice and rumbles. Silence at the edge of the screen is worse than a wall.
     */
    stacked();
    expect(getGroup()).toBeNull();
    expect(escapeGroup("card:1", "up")).toBeNull();
  });

  it("refuses inside a dialog, so the ring cannot walk out from under one", () => {
    /*
     * THE MODAL TRAP STAYS HARD. This is the guard that makes the soft trap
     * safe: a group narrows the board for comfort, a modal narrows it for
     * correctness, and only the first may give way at its edge.
     */
    stacked();
    setGroup("hand");
    const dialog = document.createElement("div");
    dialog.setAttribute("data-modal-root", "");
    dialog.innerHTML = '<button data-stop="act:ok"></button>';
    (document.querySelector(".table") as Element).append(dialog);
    boxed(dialog, 400, 200);
    boxed(dialog.firstElementChild as Element);
    expect(escapeGroup("card:1", "up")).toBeNull();
  });

  it("refuses for a mouse, which is never trapped in the first place", () => {
    stacked();
    setGroup("hand");
    document.documentElement.setAttribute("data-input", "mouse");
    expect(escapeGroup("card:1", "up")).toBeNull();
  });

  /*
   * THE WALL THAT WAS NOT A REAL WALL.
   *
   * The escape ran the SAME `pickStop` over the whole board, so the drift bound
   * that makes a column feel like a column inside a region was being applied
   * again to answer a different question -- and the player got a nudge and a
   * deny with the rest of the board plainly sitting there, off to one side.
   * `escapeGroup` retries relaxed once the strict pass comes back empty. See
   * `nav.ts:DRIFT_LIMIT` and `tests/spatialNav.test.ts`.
   */
  it("leaves the region even when the way out is off to one side", () => {
    board(["hand", "acts"]);
    const at = (el: Element, top: number, height: number, left: number, width: number) => {
      el.getBoundingClientRect = () =>
        ({
          x: left,
          y: top,
          width,
          height,
          top,
          left,
          right: left + width,
          bottom: top + height,
          toJSON() {
            return this;
          },
        }) as DOMRect;
    };
    at(document.querySelector(".table") as Element, 0, 800, 0, 1280);
    // A hand card at the left of the fan; the rail is up and a long way right,
    // which is exactly the real board's shape.
    at(document.querySelector('[data-stop="card:1"]') as Element, 600, 140, 20, 100);
    at(document.querySelector('[data-stop="act:a1"]') as Element, 500, 60, 1040, 200);
    document.documentElement.setAttribute("data-input", "pad");
    setGroup("hand");
    expect(escapeGroup("card:1", "up")).toBe("act:a1");
  });

  it("still refuses when the only candidate is behind you", () => {
    // The relaxed pass drops the drift bound and nothing else: `ALONG_MIN`
    // holds, so a wall with the whole board below it is still a wall.
    board(["hand", "acts"]);
    const at = (el: Element, top: number, height: number, left: number, width: number) => {
      el.getBoundingClientRect = () =>
        ({
          x: left,
          y: top,
          width,
          height,
          top,
          left,
          right: left + width,
          bottom: top + height,
          toJSON() {
            return this;
          },
        }) as DOMRect;
    };
    at(document.querySelector(".table") as Element, 0, 800, 0, 1280);
    at(document.querySelector('[data-stop="card:1"]') as Element, 100, 140, 20, 100);
    at(document.querySelector('[data-stop="act:a1"]') as Element, 600, 60, 1040, 200);
    document.documentElement.setAttribute("data-input", "pad");
    setGroup("hand");
    expect(escapeGroup("card:1", "up")).toBeNull();
  });
});

/*
 * WHAT THE RING MAY BE *SENT* TO, WHICH IS A WIDER SET THAN IT CAN STEP TO.
 *
 * Two questions that look like one, and the follow-up in `Table` needs the
 * second. `candidatesIn` answers "is this on screen right now", which is right
 * for a direction press: stepping does not scroll, so a row past the fold of
 * the action list is not the thing below the one you are on. A JUMP does
 * scroll -- `cursor.ts:stamp` calls `keepInView` -- so the same row is a
 * perfectly good destination.
 *
 * Asked the first way, the follow-up rejected the panel row for any blocker
 * below the fold, which is exactly the row it exists to reach when the
 * attacker's card is not drawable, and the ring stayed on the creature with
 * nothing to do. See `docs/handheld-playtest.md` Loop 9.3.
 */
describe("sendableIn", () => {
  /** A box, stated: jsdom measures nothing. */
  function at(el: Element, top: number, height: number, left = 0, width = 100): void {
    el.getBoundingClientRect = () =>
      ({
        x: left,
        y: top,
        width,
        height,
        top,
        left,
        right: left + width,
        bottom: top + height,
        toJSON() {
          return this;
        },
      }) as DOMRect;
  }

  it("takes an ordinary stop", () => {
    document.body.innerHTML = '<div class="table"><button data-stop="card:1"></button></div>';
    const table = document.querySelector(".table") as HTMLElement;
    at(table, 0, 800, 0, 1280);
    at(document.querySelector('[data-stop="card:1"]') as Element, 100, 140);
    expect([...sendableIn(table)]).toEqual(["card:1"]);
  });

  it("refuses a stop with no box of its own", () => {
    // A card mid-`AnimatePresence`-exit reports an empty rect, and the ring
    // landing on one puts it nowhere.
    document.body.innerHTML = '<div class="table"><button data-stop="card:1"></button></div>';
    const table = document.querySelector(".table") as HTMLElement;
    at(table, 0, 800, 0, 1280);
    at(document.querySelector('[data-stop="card:1"]') as Element, 100, 0);
    expect([...sendableIn(table)]).toEqual([]);
  });

  it("refuses a stop inside an ancestor clipped to nothing", () => {
    /*
     * THE CASE THE LAYOUT CREATES ON PURPOSE. An opponent's lanes are
     * `height: 0; overflow: hidden` at 1280x800 so `FxLayer` keeps its anchors,
     * and **a clipped card still reports its own full box** -- which is why
     * this is an ancestor walk rather than a size check. Nothing can scroll a
     * zero-height box into view, so this one is a real no.
     */
    document.body.innerHTML =
      '<div class="table"><div class="lanes" style="overflow: hidden">' +
      '<button data-stop="card:1"></button></div></div>';
    const table = document.querySelector(".table") as HTMLElement;
    at(table, 0, 800, 0, 1280);
    at(document.querySelector(".lanes") as Element, 100, 0);
    at(document.querySelector('[data-stop="card:1"]') as Element, 100, 140);
    expect([...sendableIn(table)]).toEqual([]);
  });

  it("TAKES a stop merely scrolled past the fold, which is the whole point", () => {
    /*
     * The row is outside its scroller's box and outside the rail's, and the
     * rail does not scroll -- so `candidatesIn` refuses it, correctly, because
     * a direction press would not reach it. A jump brings it into view.
     */
    document.body.innerHTML =
      '<div class="table"><aside class="rail" style="overflow-y: hidden">' +
      '<div class="list" style="overflow-y: auto">' +
      '<button data-stop="act:a1"></button></div></aside></div>';
    const table = document.querySelector(".table") as HTMLElement;
    at(table, 0, 800, 0, 1280);
    at(document.querySelector(".rail") as Element, 0, 300, 1000, 240);
    at(document.querySelector(".list") as Element, 0, 300, 1000, 240);
    at(document.querySelector('[data-stop="act:a1"]') as Element, 600, 40, 1000, 240);

    expect(candidatesIn(table).map((c) => c.id)).toEqual([]);
    expect([...sendableIn(table)]).toEqual(["act:a1"]);
  });
});
