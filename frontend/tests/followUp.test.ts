/**
 * Where the ring goes when the decision needs a second press.
 *
 * A table of states, like `focusGroup.test.ts`, and for the same reason: the
 * rule is a table. What is different here is that the answer is a LIST, and the
 * order of that list is the whole design -- the caller takes the first
 * candidate that is actually landable, so "the panel row is last" is what makes
 * this work at 1280x800 without knowing anything about the layout.
 *
 * So the assertions are about order and about membership, and the ones that
 * matter most are the two that would leave a player stranded: a targeting
 * gesture must always end with a panel row, and a blocker must never be sent
 * anywhere but at something it can legally block.
 */

import { describe, expect, it } from "vitest";
import type { CardView, GameView } from "../src/api/types";
import {
  blockTargetStops,
  followUpStops,
  nextBlockerStops,
  nextHandStops,
  targetStops,
} from "../src/logic/followUp";
import { action, card, gameView, player } from "./fixtures";

function creature(oid: number, controller = 0, power = 2, toughness = 2): CardView {
  return card({
    oid,
    name: `C${oid}`,
    types: ["Creature"],
    zone: "battlefield",
    controller,
    owner: controller,
    power,
    toughness,
  });
}

function inHand(oid: number): CardView {
  return card({ oid, name: `H${oid}`, zone: "hand", controller: 0, owner: 0 });
}

function view(battlefield: CardView[], hand: CardView[] = []): GameView {
  return gameView({
    seat: 0,
    battlefield,
    players: [player({ pid: 0, hand }), player({ pid: 1, hand: null })],
  });
}

const bolt = (id: string, target: number) =>
  action({ id, kind: "cast", source_oid: 99, targets: [{ kind: "object", id: target }] });

const block = (id: string, blocker: number, attacker: number) =>
  action({
    id,
    kind: "add_blocker",
    source_oid: blocker,
    targets: [{ kind: "object", id: attacker }],
  });

describe("targetStops", () => {
  it("puts an opponent's permanent before one of your own", () => {
    /*
     * A spell you aimed by hand is nearly always removal, and removal points
     * across the table. Ranking your own creature first would put the ring on
     * the one target you almost certainly did not mean.
     */
    const state = view([creature(1, 0, 5, 5), creature(2, 1, 1, 1)]);
    const actions = [bolt("x", 1), bolt("y", 2)];
    const stops = targetStops(state, actions, ["x", "y"]);
    expect(stops.indexOf("card:2")).toBeLessThan(stops.indexOf("card:1"));
  });

  it("puts the biggest of their creatures first", () => {
    const state = view([creature(1, 1, 1, 1), creature(2, 1, 6, 6)]);
    const actions = [bolt("x", 1), bolt("y", 2)];
    expect(targetStops(state, actions, ["x", "y"])[0]).toBe("card:2");
  });

  it("always ends with the panel rows, which is what stops it being a dead end", () => {
    /*
     * THE CARD IS NOT ALWAYS REACHABLE. At 1280x800 an opponent's lanes are
     * clipped to zero height, so `card:2` is in the document and not landable;
     * the caller falls through to `act:x`, which is a row in the right rail and
     * is reachable at every size.
     */
    const state = view([creature(2, 1)]);
    const stops = targetStops(state, [bolt("x", 2)], ["x"]);
    expect(stops).toEqual(["card:2", "act:x"]);
  });

  it("offers a player target as an orb", () => {
    const state = view([]);
    const shock = action({
      id: "x",
      kind: "cast",
      targets: [{ kind: "player", id: 1 }],
    });
    expect(targetStops(state, [shock], ["x"])).toEqual(["orb:1", "act:x"]);
  });

  it("puts an opponent before yourself when a spell could hit either", () => {
    const state = view([]);
    const drain = action({
      id: "x",
      kind: "cast",
      targets: [{ kind: "player", id: 0 }],
    });
    const drainThem = action({
      id: "y",
      kind: "cast",
      targets: [{ kind: "player", id: 1 }],
    });
    const stops = targetStops(state, [drain, drainThem], ["x", "y"]);
    expect(stops.indexOf("orb:1")).toBeLessThan(stops.indexOf("orb:0"));
  });

  it("ignores actions that are no longer live", () => {
    const state = view([creature(1, 1), creature(2, 1)]);
    const stops = targetStops(state, [bolt("x", 1), bolt("y", 2)], ["x"]);
    expect(stops).toEqual(["card:1", "act:x"]);
  });

  it("names each stop once however many actions aim at it", () => {
    // Kicked and unkicked at the same creature is two actions and one card.
    const state = view([creature(1, 1)]);
    const stops = targetStops(state, [bolt("x", 1), bolt("y", 1)], ["x", "y"]);
    expect(stops).toEqual(["card:1", "act:x", "act:y"]);
  });
});

describe("blockTargetStops", () => {
  it("ranks the attackers by what the block would actually achieve", () => {
    // A 3/4 kills the 2/2 and survives; the 5/5 would be a chump.
    const state = view([creature(1, 0, 3, 4), creature(2, 1, 2, 2), creature(3, 1, 5, 5)]);
    const actions = [block("b1", 1, 2), block("b2", 1, 3)];
    expect(blockTargetStops(state, actions, 1)[0]).toBe("card:2");
  });

  it("follows each attacker with its OWN row, not a block of rows at the end", () => {
    /*
     * If the card is unreachable the fallback has to be the row for THAT
     * attacker. Appending every row at the end would fall through to the wrong
     * pairing -- the ring would land on a legal press that makes the block the
     * ranking had just rejected.
     */
    const state = view([creature(1, 0, 3, 4), creature(2, 1, 2, 2), creature(3, 1, 5, 5)]);
    const actions = [block("b1", 1, 2), block("b2", 1, 3)];
    expect(blockTargetStops(state, actions, 1)).toEqual([
      "card:2",
      "act:b1",
      "card:3",
      "act:b2",
    ]);
  });

  it("offers nothing for a creature that cannot block", () => {
    const state = view([creature(1), creature(2, 1)]);
    expect(blockTargetStops(state, [], 1)).toEqual([]);
  });

  it("offers nothing for a creature that is not on the board any more", () => {
    expect(blockTargetStops(view([]), [block("b1", 1, 2)], 1)).toEqual([]);
  });
});

describe("nextBlockerStops", () => {
  it("moves on to your next creature with a job", () => {
    const actions = [block("b1", 1, 9), block("b2", 2, 9), block("b3", 3, 9)];
    expect(nextBlockerStops(actions, { 1: 9 }, 1)).toEqual(["card:2", "card:3"]);
  });

  it("skips the ones already committed", () => {
    const actions = [block("b1", 1, 9), block("b2", 2, 9)];
    expect(nextBlockerStops(actions, { 1: 9, 2: 9 }, 1)).toEqual([]);
  });

  it("never comes back to the creature just used", () => {
    const actions = [block("b1", 1, 9), block("b2", 1, 8)];
    expect(nextBlockerStops(actions, {}, 1)).toEqual([]);
  });
});

describe("nextHandStops", () => {
  it("moves to the next card you could play", () => {
    const state = view([], [inHand(1), inHand(2), inHand(3)]);
    const actions = [action({ id: "p3", kind: "cast", source_oid: 3 })];
    expect(nextHandStops(state, actions, 1)[0]).toBe("card:3");
  });

  it("STAYS IN THE HAND when nothing is playable any more", () => {
    /*
     * The land drop is the commonest gesture in the game and it spends itself,
     * so "nothing is playable now" is exactly the state it leaves behind. The
     * ring used to follow the card out of the hand and onto the battlefield,
     * where `data-group` still said `hand` and the next direction press
     * teleported back to whichever card won the scoring.
     */
    const state = view([], [inHand(1), inHand(2)]);
    expect(nextHandStops(state, [], 1)).toEqual(["card:2"]);
  });

  it("prefers a playable card, then falls back through the rest of the hand", () => {
    // The playable one first, then everything still in hand, each named once.
    const state = view([], [inHand(1), inHand(2), inHand(3)]);
    const actions = [action({ id: "p3", kind: "play_land", source_oid: 3 })];
    expect(nextHandStops(state, actions, 1)).toEqual(["card:3", "card:2"]);
  });

  it("says nothing when the hand is empty", () => {
    expect(nextHandStops(view([], [inHand(1)]), [], 1)).toEqual([]);
  });

  it("never names the card that was just played", () => {
    const state = view([], [inHand(1), inHand(2)]);
    const actions = [action({ id: "p1", kind: "play_land", source_oid: 1 })];
    expect(nextHandStops(state, actions, 1)).not.toContain("card:1");
  });
});

describe("followUpStops", () => {
  it("dispatches every gesture to its own rule", () => {
    const state = view([creature(1, 0, 3, 4), creature(2, 1, 2, 2)], [inHand(7)]);
    const actions = [block("b1", 1, 2), bolt("x", 2)];
    expect(followUpStops(state, actions, { kind: "targeting", actionIds: ["x"] })).toEqual([
      "card:2",
      "act:x",
    ]);
    expect(followUpStops(state, actions, { kind: "blocker-selected", blocker: 1 })).toEqual([
      "card:2",
      "act:b1",
    ]);
    expect(followUpStops(state, actions, { kind: "block-staged", blocker: 1 })).toEqual([]);
    expect(followUpStops(state, actions, { kind: "played-from-hand", oid: 9 })).toEqual([
      "card:7",
    ]);
  });
});
