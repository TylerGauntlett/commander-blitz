/**
 * Spatial navigation.
 *
 * The scoring is the whole of how the ring feels, and every number in it is
 * arguable. `PERP` especially: too low and "down" slides into the next column
 * whenever the card directly below happens to sit a few pixels further away;
 * too high and the ring refuses to move diagonally at all on a ragged board.
 *
 * These pin the behaviour rather than the constant, so tuning `PERP` is allowed
 * and breaking "a column stays a column" is not.
 */

import { describe, expect, it } from "vitest";
import {
  ALONG_MIN,
  type Candidate,
  type NavRect,
  PERP,
  nearestStop,
  pickStop,
  scoreStop,
  unreachableStops,
} from "../src/input/nav";

const box = (left: number, top: number, width = 100, height = 140) => ({
  left,
  top,
  width,
  height,
});

/** A tidy 3x3 grid of cards, 100x140 on a 20px gutter. */
function grid(): Candidate[] {
  const out: Candidate[] = [];
  for (let row = 0; row < 3; row += 1) {
    for (let col = 0; col < 3; col += 1) {
      out.push({ id: `r${row}c${col}`, rect: box(col * 120, row * 160) });
    }
  }
  return out;
}

describe("scoreStop", () => {
  it("rejects anything that is not in the pressed direction", () => {
    const from = box(120, 0);
    expect(scoreStop(from, box(0, 0), "right")).toBeNull();
    expect(scoreStop(from, box(240, 0), "left")).toBeNull();
  });

  it("rejects a candidate that merely overlaps", () => {
    // An attached aura sits partly under its host; without the floor it scores
    // ~0 and wins every press, so the ring would never leave the card.
    const from = box(0, 0);
    const overlapping = box(ALONG_MIN - 1, 0);
    expect(scoreStop(from, overlapping, "right")).toBeNull();
  });

  it("charges sideways drift at PERP", () => {
    const from = box(0, 0);
    const straight = scoreStop(from, box(0, 160), "down");
    const drifted = scoreStop(from, box(120, 160), "down");
    expect(straight).not.toBeNull();
    expect(drifted).not.toBeNull();
    expect((drifted as number) - (straight as number)).toBeCloseTo(120 * PERP, 6);
  });
});

describe("pickStop", () => {
  const stops = grid();
  /** The rect of a named cell, insisting it exists rather than asserting it. */
  const from = (id: string): NavRect => {
    const found = stops.find((s) => s.id === id);
    if (!found) throw new Error(`no such cell: ${id}`);
    return found.rect;
  };

  it("walks a tidy grid one cell at a time", () => {
    expect(pickStop(from("r1c1"), stops, "up", "r1c1")).toBe("r0c1");
    expect(pickStop(from("r1c1"), stops, "down", "r1c1")).toBe("r2c1");
    expect(pickStop(from("r1c1"), stops, "left", "r1c1")).toBe("r1c0");
    expect(pickStop(from("r1c1"), stops, "right", "r1c1")).toBe("r1c2");
  });

  it("returns null at a wall", () => {
    expect(pickStop(from("r0c0"), stops, "up", "r0c0")).toBeNull();
    expect(pickStop(from("r0c0"), stops, "left", "r0c0")).toBeNull();
  });

  it("keeps a column a column when the row below is ragged", () => {
    /*
     * This is the case `PERP` exists for. The card directly below is slightly
     * further away than the one diagonally below it -- which is what a lane of
     * mixed tapped and untapped permanents actually looks like, since a tapped
     * card is landscape and shorter.
     */
    const cur = box(200, 0);
    const ragged: Candidate[] = [
      { id: "below", rect: box(200, 210) },
      { id: "diagonal", rect: box(60, 170) },
    ];
    expect(pickStop(cur, ragged, "down")).toBe("below");
  });

  it("is deterministic on a tie, taking the earlier candidate", () => {
    const cur = box(100, 0);
    const tied: Candidate[] = [
      { id: "first", rect: box(0, 160) },
      { id: "second", rect: box(200, 160) },
    ];
    expect(pickStop(cur, tied, "down")).toBe("first");
  });

  it("honours the exclusion, so a stop never navigates to itself", () => {
    const cur = box(0, 0);
    const only: Candidate[] = [{ id: "self", rect: box(0, 0) }];
    expect(pickStop(cur, only, "down", "self")).toBeNull();
  });
});

describe("a row is a thing you walk along", () => {
  /*
   * THE POD'S RAIL, WHICH IS EVERY TOOLBAR IN THE APP.
   *
   * Lock in on the left, Deal on the right, and a thousand pixels of status
   * between them with nothing focusable in it. Pressing Right from Lock in went
   * UP, to the nearest chair's button, because 195px sideways plus a 166px
   * drift scores better under `PERP` than 1082px straight along the row.
   *
   * `PERP` ranks a drift against distance travelled and cannot rank a drift
   * against *being on the same line*, which is a different question and the one
   * a player is actually asking. So an aligned candidate wins outright.
   */
  const RAIL_L = { id: "lock", rect: box(24, 738, 150, 44) };
  const RAIL_R = { id: "deal", rect: box(1106, 738, 150, 44) };
  const CHAIR = { id: "chair", rect: box(886, 572, 196, 44) };

  it("crosses the whole rail rather than stepping up to a nearer neighbour", () => {
    expect(pickStop(RAIL_L.rect, [RAIL_R, CHAIR], "right")).toBe("deal");
  });

  it("does the same coming back the other way", () => {
    expect(pickStop(RAIL_R.rect, [RAIL_L, CHAIR], "left")).toBe("lock");
  });

  it("still leaves the row by the direction that leaves it", () => {
    // The rule is about which candidate wins WITHIN a direction, not about
    // trapping anything: Up from the rail is still the row above.
    expect(pickStop(RAIL_R.rect, [RAIL_L, CHAIR], "up")).toBe("chair");
  });

  it("falls back to the diagonal when the row is empty in that direction", () => {
    // Nothing beside it, so the drift-tolerant score is the only answer left --
    // and it is the right one. A rule that refused would be a wall the player
    // could walk into with somewhere obvious to go.
    expect(pickStop(RAIL_L.rect, [CHAIR], "right")).toBe("chair");
  });

  it("prefers the nearest one IN the row, not merely any of them", () => {
    const near = { id: "near", rect: box(300, 738, 150, 44) };
    expect(pickStop(RAIL_L.rect, [RAIL_R, near, CHAIR], "right")).toBe("near");
  });
});

describe("nearestStop", () => {
  it("measures to the rect rather than to its centre", () => {
    /*
     * A wide lane's centre can be further from the pointer than a card sitting
     * inside it, and the card is what the player is pointing at.
     */
    const stops: Candidate[] = [
      { id: "far", rect: box(0, 0, 40, 40) },
      { id: "near", rect: box(600, 0, 900, 40) },
    ];
    expect(nearestStop(700, 20, stops)).toBe("near");
  });

  it("breaks a containment tie toward the smaller box", () => {
    /*
     * Stops nest constantly -- a zone pile inside an orb, a defender chip
     * inside an attacker row -- so a pointer inside both is the normal case and
     * both score zero. The most specific box is the one that was meant.
     */
    const stops: Candidate[] = [
      { id: "lane", rect: box(0, 0, 900, 40) },
      { id: "badge", rect: box(840, 10, 20, 20) },
    ];
    expect(nearestStop(850, 20, stops)).toBe("badge");
  });

  it("returns null outside the snap radius, so empty felt does not drag the ring", () => {
    const stops: Candidate[] = [{ id: "card", rect: box(0, 0) }];
    expect(nearestStop(500, 500, stops, 40)).toBeNull();
    expect(nearestStop(110, 70, stops, 40)).toBe("card");
  });
});

describe("the drift limit", () => {
  /**
   * Found by building `SpatialNav.stories.tsx` rather than by writing a test.
   *
   * `PERP` ranks candidates and cannot reject one, so a lone candidate in a
   * direction wins however absurd its score. On a real board that meant "up"
   * from the leftmost creature jumping 260px sideways to a *tapped* permanent
   * -- landscape, therefore shorter, therefore its centre was 20px higher.
   */
  it("refuses a candidate that is barely ahead and wildly off to the side", () => {
    const from = box(40, 40);
    const wayOver: Candidate[] = [{ id: "tapped", rect: box(280, 40, 140, 100) }];
    expect(pickStop(from, wayOver, "up")).toBeNull();
  });

  it("still allows a genuine diagonal step to the next row", () => {
    // The thing the limit must not break: one row down and one column across.
    const from = box(160, 40);
    const diagonal: Candidate[] = [{ id: "next", rect: box(40, 220) }];
    expect(pickStop(from, diagonal, "down")).toBe("next");
  });

  it("always allows a candidate whose extent lines up, however far away", () => {
    /*
     * Alignment beats the drift bound outright. A land at the far end of a long
     * row is still directly beside the one you are on, and a limit that
     * refused it would strand stops at the ends of wide lanes.
     */
    const from = box(0, 0, 100, 140);
    const farButAligned: Candidate[] = [{ id: "far", rect: box(900, 10, 100, 140) }];
    expect(pickStop(from, farButAligned, "right")).toBe("far");
  });
});

/*
 * THE RELAXED PASS, AND THE ONE CALLER ALLOWED TO ASK FOR IT.
 *
 * `DRIFT_LIMIT` is what stops the ring lunging across the board to something
 * that merely happens to be higher, and inside a region it is never relaxed.
 * `stops.ts:escapeGroup` turns it off for a SECOND pass, after the strict one
 * has come back empty for the whole board -- at that point the player has
 * already established there is nothing on their line, and the alternative is a
 * wall with somewhere obvious to go on the other side of it.
 */
describe("the relaxed pass", () => {
  const from = box(0, 600, 100, 140);
  const acrossAndUp: Candidate[] = [{ id: "rail", rect: box(1000, 500, 200, 60) }];

  it("finds what the strict pass refuses", () => {
    expect(pickStop(from, acrossAndUp, "up")).toBeNull();
    expect(pickStop(from, acrossAndUp, "up", undefined, true)).toBe("rail");
  });

  it("still requires the candidate to be in the pressed direction", () => {
    // `ALONG_MIN` holds: relaxing the drift bound must never turn "up" into
    // "anywhere", or the ring would go backwards.
    const below: Candidate[] = [{ id: "under", rect: box(1000, 700, 200, 60) }];
    expect(pickStop(from, below, "up", undefined, true)).toBeNull();
  });

  it("still refuses the stop the ring is already on", () => {
    const self: Candidate[] = [{ id: "me", rect: from }];
    expect(pickStop(from, self, "up", "me", true)).toBeNull();
  });

  it("leaves scoreStop's ranking alone, so the nearest still wins", () => {
    const two: Candidate[] = [
      { id: "far", rect: box(1000, 100, 200, 60) },
      { id: "near", rect: box(1000, 500, 200, 60) },
    ];
    expect(pickStop(from, two, "up", undefined, true)).toBe("near");
  });

  it("changes nothing when the strict pass already had an answer", () => {
    const straightUp: Candidate[] = [
      { id: "above", rect: box(0, 400, 100, 140) },
      { id: "aside", rect: box(900, 300, 100, 140) },
    ];
    expect(pickStop(from, straightUp, "up")).toBe("above");
    expect(pickStop(from, straightUp, "up", undefined, true)).toBe("above");
  });
});

describe("unreachableStops", () => {
  it("finds nothing wrong with a tidy grid", () => {
    expect(unreachableStops(grid())).toEqual([]);
  });

  it("names a stop no press can arrive at", () => {
    /*
     * The realistic failure, and a reassuring thing to learn while writing
     * this: a stop merely far away is NOT unreachable, because the alignment
     * rule is generous along both axes. What actually strands a control is
     * sharing a centre with another one -- a badge centred on its own card, a
     * button centred in its own panel -- because then every direction scores
     * `along = 0` and the floor rejects it from everywhere.
     */
    const concentric: Candidate[] = [
      { id: "card", rect: box(0, 0, 100, 140) },
      { id: "badge-on-it", rect: box(25, 35, 50, 70) },
      { id: "neighbour", rect: box(400, 0, 100, 140) },
    ];
    expect(unreachableStops(concentric)).toEqual(["badge-on-it"]);
  });

  it("does not blame the first stop, which is placed rather than navigated to", () => {
    const two: Candidate[] = [
      { id: "first", rect: box(0, 0) },
      { id: "second", rect: box(0, 200) },
    ];
    expect(unreachableStops(two)).toEqual([]);
  });
});
