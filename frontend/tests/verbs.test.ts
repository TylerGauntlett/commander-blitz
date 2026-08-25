/**
 * The hint bar's verbs.
 *
 * A hint that disagrees with what the button actually does is worse than no
 * hint: it teaches the player a rule the game does not follow, and they only
 * find out by pressing something destructive. So what these assert is
 * *agreement* -- the verb for a stop must name the branch `Table.onBoardCard`
 * would take for that same stop, in the same order and under the same
 * predicates.
 *
 * They also assert that no verb is ever empty. A bar that goes blank reads as a
 * bar that has broken, and "nothing happens here" is a legitimate thing to say.
 */

import { describe, expect, it } from "vitest";
import type { CardView } from "../src/api/types";
import { type Staging, parseStop, verbsFor } from "../src/logic/verbs";
import { action, card, gameView, pending, player } from "../src/testing/fixtures";
import { mulligan, mulliganBottom } from "../src/testing/scenarios";

const creature = (oid: number, overrides: Partial<CardView> = {}): CardView =>
  card({
    oid,
    name: `Bear ${oid}`,
    types: ["Creature"],
    type_line: "Creature — Bear",
    zone: "battlefield",
    power: 2,
    toughness: 2,
    ...overrides,
  });

const staging = (overrides: Partial<Staging> = {}): Staging => ({
  stagedAttacks: {},
  stagedBlocks: {},
  selectedOid: null,
  targeting: false,
  ...overrides,
});

/**
 * The combobox a long decision opens with.
 *
 * A row is a HIGHLIGHT and the Choose button beside the list is the only thing
 * that acts, so the two stops say different things -- and neither says
 * "Toggle", which is what a `tool:` stop would have made the bar promise over a
 * text field.
 */
describe("a combobox's stops", () => {
  it("offers typing at the field and selecting at a row", () => {
    const state = gameView({ pending: pending({ kind: "choose_mode" }) });
    expect(verbsFor(state, [], "combo:filter").a).toBe("Type");
    expect(verbsFor(state, [], "combo:opt:a3-choose").a).toBe("Select");
  });

  it("names the action itself at the Choose button, as any act stop does", () => {
    const state = gameView({ pending: pending({ kind: "choose_mode" }) });
    const choose = action({
      id: "a3-choose",
      kind: "choose",
      label: "Vampire",
      base_label: "Vampire",
    });
    expect(verbsFor(state, [choose], "act:a3-choose").a).toBe("Vampire");
  });
});

describe("parseStop", () => {
  it("reads back the kind and payload of every namespace", () => {
    expect(parseStop("card:42")).toMatchObject({ kind: "card", id: 42 });
    expect(parseStop("orb:2")).toMatchObject({ kind: "orb", id: 2 });
    expect(parseStop("commit")).toMatchObject({ kind: "commit" });
    expect(parseStop("tool:mute")).toMatchObject({ kind: "tool" });
    expect(parseStop("pile:0:graveyard")).toMatchObject({ kind: "pile" });
    expect(parseStop("combo:filter")).toMatchObject({ kind: "combo" });
    expect(parseStop("combo:opt:a12-choose")).toMatchObject({ kind: "combo" });
  });

  it("survives an action id containing a colon, which they do", () => {
    // Action ids are opaque server strings and are not ours to constrain.
    expect(parseStop("act:a12:cast:kicked").raw).toBe("act:a12:cast:kicked");
    expect(parseStop("act:a12:cast:kicked").kind).toBe("act");
  });

  it("answers 'unknown' rather than throwing on a stop it has never seen", () => {
    expect(parseStop("something-new:1").kind).toBe("unknown");
    expect(parseStop(null).kind).toBe("unknown");
  });
});

describe("verbsFor", () => {
  it("always produces a verb for A, whatever the ring is on", () => {
    const state = gameView();
    for (const stop of [
      "card:1",
      "orb:1",
      "commit",
      "tool:mute",
      "pile:0:graveyard",
      "combo:filter",
      "junk",
    ]) {
      expect(verbsFor(state, [], stop).a.length).toBeGreaterThan(0);
    }
  });

  it("names the action a panel row would post, using base_label", () => {
    // `label` names whichever target happened to be first, which is a promise
    // the hint cannot keep. `base_label` is the card's own verb.
    const actions = [
      action({ id: "a7", kind: "cast", label: "Shock (Bear 1)", base_label: "Shock" }),
    ];
    expect(verbsFor(gameView(), actions, "act:a7").a).toBe("Shock");
  });

  describe("targeting", () => {
    const state = gameView({ battlefield: [creature(1), creature(2)] });
    const actions = [action({ id: "t1", kind: "cast", targets: [{ kind: "object", id: 1 }] })];

    it("says what pointing at a legal target would do, by name", () => {
      const verbs = verbsFor(state, actions, "card:1", staging({ targeting: true }));
      expect(verbs.a).toContain("Bear 1");
      expect(verbs.b).toBe("Cancel");
    });

    it("says plainly that an illegal target is illegal, rather than going quiet", () => {
      const verbs = verbsFor(state, actions, "card:2", staging({ targeting: true }));
      expect(verbs.a).toMatch(/not a legal target/i);
    });
  });

  describe("declare attackers", () => {
    const base = gameView({
      battlefield: [creature(1)],
      pending: pending({ kind: "declare_attackers", player: 0 }),
      players: [
        player({ pid: 0 }),
        player({ pid: 1, name: "Edgar" }),
        player({ pid: 2, name: "Duelist" }),
      ],
    });
    const attack = (defenders: number[]) =>
      defenders.map((pid) =>
        action({
          id: `atk-${pid}`,
          kind: "add_attacker",
          source_oid: 1,
          targets: [{ kind: "player", id: pid }],
        }),
      );

    it("offers Attack on an unstaged creature that has somewhere to go", () => {
      expect(verbsFor(base, attack([1]), "card:1", staging()).a).toBe("Attack");
    });

    it("offers Withdraw on a staged one, matching the click's plain toggle", () => {
      const verbs = verbsFor(base, attack([1]), "card:1", staging({ stagedAttacks: { 1: 1 } }));
      expect(verbs.a).toBe("Withdraw");
    });

    it("only offers X to re-aim when there is a second seat to aim at", () => {
      /*
       * A pod is the case; a duel is not. Advertising a re-aim that cycles back
       * to the same opponent is a button that appears to do nothing.
       *
       * With one seat `X` is free, so it falls through to the commit -- which
       * is the point of the fall-through: on a staged attacker with nowhere
       * else to point, the thing you want is to send it.
       */
      const one = verbsFor(base, attack([1]), "card:1", staging({ stagedAttacks: { 1: 1 } }));
      expect(one.x).not.toContain("Re-aim");
      expect(one.x).toBe("Attack");
      const two = verbsFor(
        base,
        attack([1, 2]),
        "card:1",
        staging({ stagedAttacks: { 1: 1 } }),
      );
      expect(two.x).toContain("Re-aim");
    });

    it("names the seat an attacker would be pointed at", () => {
      const verbs = verbsFor(base, attack([1, 2]), "orb:1", staging({ selectedOid: 1 }));
      expect(verbs.a).toBe("Attack Edgar");
    });
  });

  describe("declare blockers", () => {
    const base = gameView({
      battlefield: [creature(1), creature(2, { attacking: true, controller: 1 })],
      pending: pending({ kind: "declare_blockers", player: 0 }),
    });
    const actions = [
      action({
        id: "blk",
        kind: "add_blocker",
        source_oid: 1,
        targets: [{ kind: "object", id: 2 }],
      }),
    ];

    it("offers the blocker first, then the attacker it stops", () => {
      // Step one: pick your creature.
      expect(verbsFor(base, actions, "card:1", staging()).a).toBe("Block with");
      // Step two: with it selected, the attacker says what blocking achieves.
      const aimed = verbsFor(base, actions, "card:2", staging({ selectedOid: 1 }));
      expect(aimed.a).toContain("Block");
      expect(aimed.a).toContain("Bear 2");
    });

    it("offers Deselect on the creature already picked, since every step reverses", () => {
      expect(verbsFor(base, actions, "card:1", staging({ selectedOid: 1 })).a).toBe("Deselect");
    });

    it("offers Release on a blocker already committed", () => {
      expect(verbsFor(base, actions, "card:1", staging({ stagedBlocks: { 1: 2 } })).a).toBe(
        "Release",
      );
    });

    it("offers to clear everything aimed at an attacker", () => {
      expect(verbsFor(base, actions, "card:2", staging({ stagedBlocks: { 1: 2 } })).a).toBe(
        "Clear blocks",
      );
    });
  });

  describe("play mode", () => {
    it("says the verb and not the card's name, and offers X when it also has an ability", () => {
      /*
       * `base_label` is "Cast Bear", and the bar is one line shared with the
       * navigation half -- a real card name wrapped it. The ring is on the card
       * and the reader is showing the card, so the name is the half the hint
       * does not have to carry.
       */
      const state = gameView({ battlefield: [creature(1)] });
      const cast = action({ id: "c", kind: "cast", source_oid: 1, base_label: "Cast Bear" });
      expect(verbsFor(state, [cast], "card:1").a).toBe("Cast");
      expect(verbsFor(state, [cast], "card:1").x).toBeUndefined();

      const withAbility = [cast, action({ id: "b", kind: "activate", source_oid: 1 })];
      expect(verbsFor(state, withAbility, "card:1").x).toBe("Activate");
    });

    it("keeps Play for a land, because playing one is not casting one", () => {
      const state = gameView({ battlefield: [creature(1)] });
      const land = action({
        id: "l",
        kind: "play_land",
        source_oid: 1,
        base_label: "Play Blood Crypt",
      });
      expect(verbsFor(state, [land], "card:1").a).toBe("Play");
    });

    it("does not promise one ability's name when a permanent offers several", () => {
      /*
       * The same reasoning `Table`'s `abilityLabels` gives: naming the first of
       * several is a promise the hint cannot keep, since a Mind Stone offers a
       * mana ability and a sacrifice ability and either might be meant.
       */
      const state = gameView({ battlefield: [creature(1)] });
      const actions = [
        action({ id: "m", kind: "activate", source_oid: 1, base_label: "{T}: Add {C}" }),
        action({ id: "s", kind: "activate", source_oid: 1, base_label: "Sacrifice" }),
      ];
      expect(verbsFor(state, actions, "card:1").a).toBe("Abilities");
    });

    it("falls back to Read on a card with nothing to do", () => {
      const state = gameView({ battlefield: [creature(1)] });
      expect(verbsFor(state, [], "card:1").a).toBe("Read");
    });
  });

  /*
   * X FALLS THROUGH TO PASS.
   *
   * Passing is the most repeated action in the game and it had no button: a
   * keyboard has had `Space` since before any of this existed, and a pad paid
   * `L2` then `A` for every priority window of every turn. `X` is empty on most
   * stops, so it takes the job rather than a button being invented for it.
   *
   * What these pin is the agreement with `Table.secondary`, which is the whole
   * point of this file: the fall-through has to be LAST, so nothing that
   * already had a secondary loses it.
   */
  describe("X, where it has nothing else to do", () => {
    const pass = action({ id: "p", kind: "pass" });

    it("passes from any stop with no secondary of its own", () => {
      const state = gameView({ battlefield: [creature(1)] });
      for (const stop of ["card:1", "orb:1", "tool:mute", "pile:0:graveyard", "lane:0:Lands"]) {
        expect(verbsFor(state, [pass], stop).x).toBe("Pass");
      }
    });

    it("says nothing when the ring is already on the control it would press", () => {
      /*
       * `A Pass  X Pass` is a one-line bar saying one thing twice, and the bar
       * is short of room. `X` is a shortcut TO the dock; standing on the dock
       * you already have `A`.
       */
      const state = gameView({ battlefield: [creature(1)] });
      expect(verbsFor(state, [pass], "commit").x).toBeUndefined();
      expect(verbsFor(state, [pass], "commit:all").x).toBeUndefined();
      expect(verbsFor(state, [pass], "act:p").x).toBeUndefined();
    });

    it("says nothing when passing is not legal", () => {
      const state = gameView({ battlefield: [creature(1)] });
      expect(verbsFor(state, [], "card:1").x).toBeUndefined();
    });

    it("never displaces Activate", () => {
      const state = gameView({ battlefield: [creature(1)] });
      const actions = [
        pass,
        action({ id: "c", kind: "cast", source_oid: 1 }),
        action({ id: "b", kind: "activate", source_oid: 1 }),
      ];
      expect(verbsFor(state, actions, "card:1").x).toBe("Activate");
    });

    it("never displaces Re-aim", () => {
      const state = gameView({
        battlefield: [creature(1)],
        pending: pending({ kind: "declare_attackers", player: 0 }),
        players: [player({ pid: 0 }), player({ pid: 1 }), player({ pid: 2 })],
      });
      const actions = [
        pass,
        action({
          id: "s1",
          kind: "add_attacker",
          source_oid: 1,
          targets: [{ kind: "player", id: 1 }],
        }),
        action({
          id: "s2",
          kind: "add_attacker",
          source_oid: 1,
          targets: [{ kind: "player", id: 2 }],
        }),
      ];
      const verbs = verbsFor(state, actions, "card:1", staging({ stagedAttacks: { 1: 1 } }));
      expect(verbs.x).toMatch(/Re-aim/);
    });

    it("stays quiet on the opening hand, where there is no priority to pass", () => {
      const { state, actions } = mulligan();
      expect(verbsFor(state, actions, "card:101").x).toBeUndefined();
    });
  });

  /*
   * The combat dock, whose two local controls are `commit` stops.
   *
   * Neither the "all" mark nor the slab is a server action -- they stage into
   * `uiStore` and declare what is staged -- so there is no `base_label` to read
   * and the verb is written by hand. It is written to match the button's own
   * words, because `A Confirm` printed over a button reading `Attack` is
   * exactly the small lie this whole file exists to stop.
   */
  describe("on the combat bar", () => {
    const declaring = (kind: "declare_attackers" | "declare_blockers") =>
      gameView({ pending: pending({ kind, player: 0 }), players: [player({ pid: 0 })] });

    it("names the mark after the decision it answers outright", () => {
      expect(verbsFor(declaring("declare_attackers"), [], "commit:all").a).toBe("All attack");
      expect(verbsFor(declaring("declare_blockers"), [], "commit:all").a).toBe("All defend");
    });

    it("names the slab after the word printed on it", () => {
      expect(verbsFor(declaring("declare_attackers"), [], "commit").a).toBe("Attack");
      expect(verbsFor(declaring("declare_blockers"), [], "commit").a).toBe("Block");
    });

    it("falls back to Confirm off combat, where the slab has no combat word", () => {
      expect(verbsFor(gameView(), [], "commit").a).toBe("Confirm");
      expect(verbsFor(gameView(), [], "commit:all").a).toBe("All");
    });
  });

  it("offers Read wherever there is a card to read", () => {
    const state = gameView({ battlefield: [creature(1)] });
    expect(verbsFor(state, [], "card:1").y).toBe("Read");
  });

  it("has no Back on the commit slab's parent decision but always offers one on a card", () => {
    // `B` is a strict unwind and never quits from the top; a card is never the
    // top, so it always has somewhere to go back to.
    expect(verbsFor(gameView(), [], "card:1").b).toBe("Back");
  });

  /*
   * The opening hand, where two of the rules above stop holding.
   *
   * A card in your opening hand has no legal action of its own, so every branch
   * in the file would fall through to `A Read` -- and what `A` does there is
   * keep the hand. And `B Back` is on almost every other branch, which is true
   * on a board and false on a screen where `B` mulligans.
   */
  describe("during a mulligan", () => {
    const keepPhase = () => {
      const s = mulligan();
      return { state: s.state, actions: s.actions };
    };

    it("says Keep on a hand card, because that is what A does there", () => {
      const { state, actions } = keepPhase();
      expect(verbsFor(state, actions, "card:101").a).toBe("Keep");
    });

    it("says Mulligan on B from every stop, because B is bound to it", () => {
      const { state, actions } = keepPhase();
      expect(verbsFor(state, actions, "card:101").b).toBe("Mulligan");
      expect(verbsFor(state, actions, "act:a0-keep").b).toBe("Mulligan");
      expect(verbsFor(state, actions, null).b).toBe("Mulligan");
    });

    it("names the button the ring is actually on", () => {
      const { state, actions } = keepPhase();
      expect(verbsFor(state, actions, "act:a0-keep").a).toBe("Keep");
      expect(verbsFor(state, actions, "act:a1-mulligan").a).toBe("Mulligan");
    });

    it("still offers Read on a card, since the neighbour crops the art", () => {
      const { state, actions } = keepPhase();
      expect(verbsFor(state, actions, "card:101").y).toBe("Read");
      // ...and not on a button, where `Table`'s Y binding does nothing.
      expect(verbsFor(state, actions, "act:a0-keep").y).toBeUndefined();
    });

    it("drops B entirely while bottoming, because nothing un-picks", () => {
      const { state, actions } = mulliganBottom();
      const verbs = verbsFor(state, actions, "act:a0-bottom");
      expect(verbs.a).toBe(state.players[0].hand?.[0].name);
      expect(verbs.b).toBeUndefined();
    });
  });
});
