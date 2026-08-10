import { describe, expect, it } from "vitest";
import {
  actionsForCard,
  availableAttackers,
  blockableBy,
  canDropOnLane,
  defendersFor,
  dropTargets,
  groupPlayActions,
  isOurDecision,
  needsTargetChoice,
  resolveSingleAction,
} from "../src/logic/actionMatch";
import { LANES } from "../src/logic/zoneGrouping";
import { action, card, gameView, player } from "./fixtures";

const bear = card({ oid: 10, zone: "hand", types: ["Creature"] });
const forest = card({ oid: 11, zone: "hand", types: ["Land"], name: "Forest" });
const bolt = card({ oid: 12, zone: "hand", types: ["Instant"], name: "Bolt" });

function stateWithHand() {
  return gameView({
    players: [player({ hand: [bear, forest, bolt] }), player({ pid: 1, hand: null })],
  });
}

describe("actionsForCard", () => {
  it("finds plays for the right card only", () => {
    const actions = [
      action({ id: "a1", kind: "cast", source_oid: 10 }),
      action({ id: "a2", kind: "play_land", source_oid: 11 }),
      action({ id: "a3", kind: "pass" }),
    ];
    expect(actionsForCard(actions, 10).map((a) => a.id)).toEqual(["a1"]);
    expect(actionsForCard(actions, 11).map((a) => a.id)).toEqual(["a2"]);
    expect(actionsForCard(actions, 99)).toEqual([]);
  });

  it("ignores actions that are not plays", () => {
    const actions = [action({ id: "a1", kind: "activate", source_oid: 10 })];
    expect(actionsForCard(actions, 10)).toEqual([]);
  });
});

describe("canDropOnLane", () => {
  const state = stateWithHand();

  it("accepts a creature onto the creature lane", () => {
    const actions = [action({ id: "a1", kind: "cast", source_oid: 10 })];
    expect(canDropOnLane(state, actions, 10, "Creatures")).toBe(true);
    expect(canDropOnLane(state, actions, 10, "Lands")).toBe(false);
  });

  it("accepts a land only onto the land lane", () => {
    const actions = [action({ id: "a2", kind: "play_land", source_oid: 11 })];
    expect(canDropOnLane(state, actions, 11, "Lands")).toBe(true);
    expect(canDropOnLane(state, actions, 11, "Creatures")).toBe(false);
  });

  it("lets a spell land anywhere, since it has no lane of its own", () => {
    const actions = [action({ id: "a3", kind: "cast", source_oid: 12 })];
    for (const lane of LANES) {
      expect(canDropOnLane(state, actions, 12, lane)).toBe(true);
    }
  });

  it("refuses anything with no legal action behind it", () => {
    expect(canDropOnLane(state, [], 10, "Creatures")).toBe(false);
  });

  it("refuses a card that is not in hand", () => {
    const actions = [action({ id: "a1", kind: "cast", source_oid: 77 })];
    expect(canDropOnLane(state, actions, 77, "Creatures")).toBe(false);
  });
});

describe("dropTargets", () => {
  it("highlights exactly the legal lanes", () => {
    const state = stateWithHand();
    const actions = [action({ id: "a2", kind: "play_land", source_oid: 11 })];
    expect(dropTargets(state, actions, 11, LANES)).toEqual(["Lands"]);
  });
});

describe("target disambiguation", () => {
  it("resolves a single untargeted play immediately", () => {
    const actions = [action({ id: "a1", kind: "cast", source_oid: 10 })];
    expect(needsTargetChoice(actions, 10)).toBe(false);
    expect(resolveSingleAction(actions, 10)?.id).toBe("a1");
  });

  it("requires a choice when several targets are offered", () => {
    const actions = [
      action({ id: "a1", kind: "cast", source_oid: 12, targets: [{ kind: "object", id: 1 }] }),
      action({ id: "a2", kind: "cast", source_oid: 12, targets: [{ kind: "object", id: 2 }] }),
    ];
    expect(needsTargetChoice(actions, 12)).toBe(true);
    expect(resolveSingleAction(actions, 12)).toBeNull();
  });

  it("still asks when a single option carries a target", () => {
    const actions = [
      action({ id: "a1", kind: "cast", source_oid: 12, targets: [{ kind: "object", id: 1 }] }),
    ];
    expect(needsTargetChoice(actions, 12)).toBe(true);
  });
});

describe("groupPlayActions", () => {
  /** One card in hand, `n` creatures on the board: the engine offers it `n` times. */
  const aimedAt = (ids: number[], overrides: Partial<Parameters<typeof action>[0]> = {}) =>
    ids.map((id) =>
      action({
        id: `a${id}-cast`,
        kind: "cast",
        label: `Cast Simic Charm -> #${id}`,
        base_label: "Cast Simic Charm",
        source_oid: 12,
        targets: [{ kind: "object", id }],
        ...overrides,
      }),
    );

  it("collapses one card's target variants into a single row", () => {
    // The reported bug: six identical-looking Simic Charm rows in the panel.
    const groups = groupPlayActions(aimedAt([3, 1, 2, 5, 4, 6]));
    expect(groups).toHaveLength(1);
    expect(groups[0].actions).toHaveLength(6);
    expect(groups[0].head.base_label).toBe("Cast Simic Charm");
  });

  it("orders the chips by target, so a poll cannot move them", () => {
    const groups = groupPlayActions(aimedAt([3, 1, 2]));
    expect(groups[0].actions.map((a) => a.targets[0].id)).toEqual([1, 2, 3]);
  });

  it("puts declining an optional target last", () => {
    const groups = groupPlayActions([
      ...aimedAt([2, 1]),
      action({
        id: "a0-cast",
        kind: "cast",
        label: "Cast Simic Charm",
        base_label: "Cast Simic Charm",
        source_oid: 12,
      }),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].actions.map((a) => a.id)).toEqual(["a1-cast", "a2-cast", "a0-cast"]);
  });

  it("keeps kicked and unkicked apart", () => {
    // Two different things to do with one card, and `base_label` is what says so.
    const groups = groupPlayActions([
      ...aimedAt([1, 2]),
      ...aimedAt([1, 2], { base_label: "Cast Simic Charm (kicked)" }),
    ]);
    expect(groups).toHaveLength(2);
    expect(groups.map((g) => g.actions.length)).toEqual([2, 2]);
  });

  it("keeps two copies of the same card in hand apart", () => {
    // docs/bugs.md: deduplicating by card rather than by object is what made
    // the second and third Forest in hand unclickable.
    const groups = groupPlayActions([
      action({ id: "a1", kind: "play_land", label: "Play Forest", source_oid: 20 }),
      action({ id: "a2", kind: "play_land", label: "Play Forest", source_oid: 21 }),
    ]);
    expect(groups).toHaveLength(2);
  });

  it("keeps two abilities of one permanent apart", () => {
    const groups = groupPlayActions([
      action({
        id: "a1",
        kind: "activate",
        source_oid: 30,
        ability_index: 0,
        base_label: "Heirloom: {T}: trample",
      }),
      action({
        id: "a2",
        kind: "activate",
        source_oid: 30,
        ability_index: 1,
        base_label: "Heirloom: {T}: hexproof",
      }),
    ]);
    expect(groups).toHaveLength(2);
  });

  it("leaves untargeted actions one to a row", () => {
    const groups = groupPlayActions([
      action({ id: "a1", kind: "pass", label: "Pass", base_label: "Pass" }),
      action({
        id: "a2",
        kind: "cast",
        label: "Cast Bear",
        base_label: "Cast Bear",
        source_oid: 9,
      }),
    ]);
    expect(groups.map((g) => g.actions.length)).toEqual([1, 1]);
  });

  it("preserves the server's row order", () => {
    const groups = groupPlayActions([
      action({ id: "a1", kind: "play_land", label: "Play Forest", source_oid: 20 }),
      ...aimedAt([2, 1]),
      action({ id: "a9", kind: "pass", label: "Pass", base_label: "Pass" }),
    ]);
    expect(groups.map((g) => g.head.id)).toEqual(["a1", "a2-cast", "a9"]);
  });
});

describe("combat helpers", () => {
  const actions = [
    action({
      id: "a1",
      kind: "add_attacker",
      source_oid: 5,
      targets: [{ kind: "player", id: 1 }],
    }),
    action({
      id: "a2",
      kind: "add_attacker",
      source_oid: 5,
      targets: [{ kind: "player", id: 2 }],
    }),
    action({
      id: "a3",
      kind: "add_attacker",
      source_oid: 6,
      targets: [{ kind: "player", id: 1 }],
    }),
    action({
      id: "a4",
      kind: "add_blocker",
      source_oid: 9,
      targets: [{ kind: "object", id: 5 }],
    }),
    action({ id: "a5", kind: "finish_declaration" }),
  ];

  it("lists each attacker once", () => {
    expect(availableAttackers(actions)).toEqual([5, 6]);
  });

  it("lists every defender an attacker may be sent at", () => {
    expect(defendersFor(actions, 5)).toEqual([1, 2]);
    expect(defendersFor(actions, 6)).toEqual([1]);
  });

  it("lists what a blocker may block", () => {
    expect(blockableBy(actions, 9)).toEqual([5]);
    expect(blockableBy(actions, 99)).toEqual([]);
  });
});

describe("isOurDecision", () => {
  it("is true only when the pending decision belongs to the viewer", () => {
    expect(isOurDecision(gameView())).toBe(true);
    const theirs = gameView({
      pending: {
        kind: "priority",
        player: 1,
        prompt: "",
        options: [],
        min_count: 1,
        max_count: 1,
        selected: [],
        allow_done: true,
        context: {},
      },
    });
    expect(isOurDecision(theirs)).toBe(false);
    expect(isOurDecision(gameView({ pending: null }))).toBe(false);
  });
});
