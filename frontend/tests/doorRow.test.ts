/**
 * The front door's row, as arithmetic.
 *
 * Everything on that screen is a function of one number, so the whole of it can
 * be checked without a DOM -- which is the point of `logic/doorRow.ts` being a
 * separate file. What these pin are the four claims the design rests on: the
 * middle card is centred when it is selected, the far card BUNCHES back over its
 * neighbour rather than fanning evenly, the stack order falls with distance, and
 * a card two places out has faded its copy before anything covers it.
 */

import { describe, expect, it } from "vitest";
import { DOOR_TUNE, poseOf, scaleTune, stageScale } from "../src/logic/doorRow";

const pose = (i: number, s: number) => poseOf(i, s, DOOR_TUNE);

describe("the row at rest", () => {
  it("centres the selected card, whichever it is", () => {
    expect(pose(1, 1).x).toBe(0);
    // Selecting an end does not move that card to the middle -- the row is laid
    // out about its own centre, and the selected card is where it always was.
    expect(pose(0, 0).x).toBe(-DOOR_TUNE.STEP);
    expect(pose(2, 2).x).toBe(DOOR_TUNE.STEP);
  });

  it("lifts, grows and squares up only the selected card", () => {
    const on = pose(1, 1);
    expect(on.y).toBe(-DOOR_TUNE.LIFT);
    expect(on.rot).toBe(0);
    expect(on.scale).toBeCloseTo(1 + DOOR_TUNE.RAISE);

    const off = pose(0, 1);
    expect(off.y).toBe(DOOR_TUNE.DROOP);
    expect(off.rot).toBe(-DOOR_TUNE.ARC);
    expect(off.scale).toBe(1);
  });

  it("pushes a neighbour away and pulls the far card back over it", () => {
    // One place out: pushed away, full stop. This is a fan.
    expect(pose(0, 1).x).toBe(-DOOR_TUNE.STEP - DOOR_TUNE.PUSH);

    // Two places out: pushed, then BUNCHED back. This is the stack, and it is
    // the only new term in the whole arithmetic.
    expect(pose(2, 0).x).toBe(DOOR_TUNE.STEP + DOOR_TUNE.PUSH - DOOR_TUNE.BUNCH);
  });

  it("leaves the far card a sliver wider than the longest label", () => {
    // Of two cards on the same side the nearer is drawn on top, so what is left
    // of the further one is this wide. `Decks` is the longest name on the
    // screen and measures 88px at 20px/800/0.16em; the mockup round failed the
    // file at 108 and settled on this.
    const sliver = DOOR_TUNE.STEP - DOOR_TUNE.BUNCH;
    expect(sliver).toBeGreaterThan(88);
  });

  it("draws the nearer of two stacked cards on top", () => {
    expect(pose(1, 0).z).toBeGreaterThan(pose(2, 0).z);
    expect(pose(0, 0).z).toBeGreaterThan(pose(1, 0).z);
  });
});

describe("the row in flight", () => {
  it("is continuous -- no term jumps between two settled states", () => {
    let previous = pose(0, 1);
    for (let s = 1; s >= 0; s -= 0.02) {
      const now = pose(0, s);
      expect(Math.abs(now.x - previous.x)).toBeLessThan(DOOR_TUNE.STEP * 0.1);
      expect(Math.abs(now.rot - previous.rot)).toBeLessThan(1);
      expect(Math.abs(now.scale - previous.scale)).toBeLessThan(0.05);
      previous = now;
    }
  });

  it("fits inside a 1280px stage in its widest state", () => {
    // The widest state is NOT the one the row opens on: selecting an end pushes
    // the far pair outward. `.door` is `overflow: hidden`, so a row that ran off
    // it would report no page overflow at all.
    const halfCard = 200 / 2;
    for (const s of [0, 1, 2]) {
      const xs = [0, 1, 2].map((i) => pose(i, s));
      const left = Math.min(...xs.map((p) => p.x - halfCard * p.scale));
      const right = Math.max(...xs.map((p) => p.x + halfCard * p.scale));
      expect(right - left).toBeLessThan(1280);
    }
  });
});

describe("the stage scale", () => {
  it("is exactly 1 at the Deck's own 1280x800", () => {
    expect(stageScale(1280, 800)).toBe(1);
  });

  it("grows on a desktop and stops before the row outgrows the room", () => {
    expect(stageScale(1600, 950)).toBeCloseTo(1.1875);
    expect(stageScale(3840, 2160)).toBe(1.45);
  });

  it("shrinks on a small window rather than clipping", () => {
    expect(stageScale(1024, 640)).toBeCloseTo(0.8);
    expect(stageScale(1024, 520)).toBe(0.72);
  });

  it("goes further down on a phone, whose screen is shorter than the 0.72 stage", () => {
    // A phone held sideways: 0.72 laid the stage out 576px tall on a 428px
    // screen, and the opening hand's Keep landed off the bottom edge.
    expect(stageScale(926, 428)).toBeCloseTo(428 / 800);
    expect(stageScale(580, 900)).toBeCloseTo(580 / 1280);
    // ...and a narrow phone held upright reaches the phone floor.
    expect(stageScale(390, 844)).toBe(0.4);
  });

  it("scales the five distances and neither of the two unitless terms", () => {
    const bigger = scaleTune(DOOR_TUNE, 1.25);
    expect(bigger.STEP).toBe(DOOR_TUNE.STEP * 1.25);
    expect(bigger.BUNCH).toBe(DOOR_TUNE.BUNCH * 1.25);
    expect(bigger.LIFT).toBe(DOOR_TUNE.LIFT * 1.25);
    // A tilt is an angle and a raise is a ratio: both are already relative.
    expect(bigger.ARC).toBe(DOOR_TUNE.ARC);
    expect(bigger.RAISE).toBe(DOOR_TUNE.RAISE);
  });
});

/**
 * The row grew a fourth card, and the arithmetic was written for three.
 *
 * Both terms that had to change are identities at three -- which is why every
 * test above still calls `poseOf` the way it always did, and why they are the
 * real guard here. These cover what only exists at four.
 */
describe("a row of four", () => {
  const pose4 = (i: number, s: number) => poseOf(i, s, DOOR_TUNE, 4);

  it("is centred on the row rather than on index 1", () => {
    /*
     * `x` was `(i - 1) * STEP`, which centres a row of three and shifts a row of
     * four half a step right -- the whole menu off-centre in its pool of light,
     * with nothing in the suite looking at absolute position.
     */
    const outer = pose4(0, 1.5).x + pose4(3, 1.5).x;
    expect(Math.abs(outer)).toBeLessThan(0.001);
    const inner = pose4(1, 1.5).x + pose4(2, 1.5).x;
    expect(Math.abs(inner)).toBeLessThan(0.001);
  });

  it("keeps the row in order when an end card is selected", () => {
    /*
     * THE BUNCH CLAMP. `far` was unbounded, so at three places from the
     * selection a card took `BUNCH * 2` of pull-back and slid clean THROUGH the
     * neighbour it was supposed to hide behind, inverting the stack. A row of
     * three never reaches three places, which is why it went unnoticed.
     */
    for (const sel of [0, 1, 2, 3]) {
      const xs = [0, 1, 2, 3].map((i) => pose4(i, sel).x);
      for (let i = 1; i < xs.length; i += 1) {
        expect(xs[i], `card ${i} overtook ${i - 1} with ${sel} selected`).toBeGreaterThan(
          xs[i - 1],
        );
      }
    }
  });

  it("still lifts exactly the selected card", () => {
    for (const sel of [0, 1, 2, 3]) {
      const scales = [0, 1, 2, 3].map((i) => pose4(i, sel).scale);
      expect(scales[sel]).toBeCloseTo(1 + DOOR_TUNE.RAISE, 6);
      for (const i of [0, 1, 2, 3].filter((n) => n !== sel)) {
        expect(scales[i]).toBeLessThan(scales[sel]);
      }
    }
  });

  it("agrees with the three-card row when asked for one", () => {
    // The default is three, and every existing case relies on it.
    for (const i of [0, 1, 2]) {
      expect(poseOf(i, 1, DOOR_TUNE, 3)).toEqual(poseOf(i, 1, DOOR_TUNE));
    }
  });
});
