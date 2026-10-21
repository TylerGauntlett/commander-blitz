/**
 * What a press on a permanent with activated abilities means.
 *
 * One router for the board press and for `X`, so the two cannot disagree --
 * which they did: the click selected a Mind Stone and `X` tapped it for mana
 * without asking, with the sacrifice ability one index away.
 */

import { describe, expect, it } from "vitest";
import { abilitiesOf, abilityRoute, routeFor } from "../src/logic/abilities";
import { action } from "../src/testing/fixtures";
import { twoAbilityPermanent } from "../src/testing/scenarios";

const activate = (id: string, index: number, text: string, targets: number[] = []) =>
  action({
    id,
    kind: "activate",
    label: targets.length ? `Stone: ${text} -> ${targets[0]}` : `Stone: ${text}`,
    base_label: `Stone: ${text}`,
    source_oid: 7,
    ability_index: index,
    targets: targets.map((oid) => ({ kind: "object", id: oid })),
  });

describe("abilityRoute", () => {
  it("offers nothing for a permanent with no abilities", () => {
    expect(abilityRoute([action({ kind: "pass" })], 7)).toEqual({ kind: "none" });
  });

  it("posts a lone untargeted ability straight away", () => {
    expect(abilityRoute([activate("a1", 0, "{T}: Add {C}")], 7)).toEqual({
      kind: "act",
      id: "a1",
    });
  });

  it("enters targeting on exactly one ability's ids when it needs a target", () => {
    const actions = [
      activate("a1", 0, "{T}: Tap target creature.", [11]),
      activate("a2", 0, "{T}: Tap target creature.", [12]),
    ];
    expect(abilityRoute(actions, 7)).toEqual({ kind: "target", ids: ["a1", "a2"] });
  });

  it("asks which yield when one ability makes several, as a Treasure does", () => {
    // "Add one mana of any colour" is five actions that target nothing. The
    // board asks which colour, rather than sending the ring to the panel.
    const actions = ["{W}", "{U}", "{B}"].map((c, i) => ({
      ...activate(`a${i}`, 0, "{T}, Sacrifice this artifact: Add one mana of any color."),
      option_label: c,
    }));
    const route = abilityRoute(actions, 7);
    expect(route.kind).toBe("menu");
    if (route.kind !== "menu") return;
    expect(route.abilities.map((a) => a.text)).toEqual(["{W}", "{U}", "{B}"]);
    expect(route.abilities.map((a) => a.key)).toEqual(["0-yield-0", "0-yield-1", "0-yield-2"]);
    expect(route.abilities.map((a) => routeFor(a))).toEqual([
      { kind: "act", id: "a0" },
      { kind: "act", id: "a1" },
      { kind: "act", id: "a2" },
    ]);
  });

  it("asks which ability first, then which yield", () => {
    // Commander's Sphere: a colour ability and a sacrifice ability.
    const actions = [
      ...["{G}", "{U}"].map((c, i) => ({
        ...activate(
          `m${i}`,
          0,
          "{T}: Add one mana of any color in your commander's color identity.",
        ),
        option_label: c,
      })),
      activate("d1", 1, "Sacrifice this artifact: Draw a card."),
    ];
    const route = abilityRoute(actions, 7);
    expect(route.kind).toBe("menu");
    if (route.kind !== "menu") return;
    expect(route.abilities).toHaveLength(2);
    const colours = routeFor(route.abilities[0]);
    expect(colours.kind).toBe("menu");
    if (colours.kind !== "menu") return;
    expect(colours.abilities.map((a) => [a.text, routeFor(a)])).toEqual([
      ["{G}", { kind: "act", id: "m0" }],
      ["{U}", { kind: "act", id: "m1" }],
    ]);
    expect(routeFor(route.abilities[1])).toEqual({ kind: "act", id: "d1" });
  });

  it("keeps a yield's targets behind its item", () => {
    const actions = [
      { ...activate("a1", 0, "{T}: Add one mana of any color.", [11]), option_label: "{R}" },
      { ...activate("a2", 0, "{T}: Add one mana of any color.", [12]), option_label: "{R}" },
      { ...activate("a3", 0, "{T}: Add one mana of any color.", [11]), option_label: "{G}" },
    ];
    const route = abilityRoute(actions, 7);
    expect(route.kind).toBe("menu");
    if (route.kind !== "menu") return;
    expect(route.abilities.map((a) => routeFor(a))).toEqual([
      { kind: "target", ids: ["a1", "a2"] },
      { kind: "target", ids: ["a3"] },
    ]);
  });

  it("does not ask when every copy yields the same thing", () => {
    const actions = [
      { ...activate("a1", 0, "{T}: Add {R}.", [11]), option_label: "{R}" },
      { ...activate("a2", 0, "{T}: Add {R}.", [12]), option_label: "{R}" },
    ];
    expect(abilityRoute(actions, 7)).toEqual({ kind: "target", ids: ["a1", "a2"] });
  });

  it("asks which ability when there are two, with the card's name taken off", () => {
    const { actions } = twoAbilityPermanent();
    const route = abilityRoute(actions, 401, "Mind Stone");
    expect(route.kind).toBe("menu");
    if (route.kind !== "menu") return;
    expect(route.abilities.map((a) => a.text)).toEqual([
      "{T}: Add {C}",
      "{1}, {T}, Sacrifice this artifact: Draw a card.",
    ]);
    expect(route.abilities.map((a) => a.ids)).toEqual([["a1-activate"], ["a2-activate"]]);
    expect(route.abilities.map((a) => a.targeted)).toEqual([false, false]);
  });

  it("groups a targeted ability's variants under one menu item", () => {
    const actions = [
      activate("a1", 0, "{T}: Add {C}"),
      activate("a2", 1, "{T}: Tap target creature.", [11]),
      activate("a3", 1, "{T}: Tap target creature.", [12]),
    ];
    const route = abilityRoute(actions, 7);
    expect(route.kind).toBe("menu");
    if (route.kind !== "menu") return;
    expect(route.abilities).toHaveLength(2);
    expect(routeFor(route.abilities[0])).toEqual({ kind: "act", id: "a1" });
    expect(routeFor(route.abilities[1])).toEqual({ kind: "target", ids: ["a2", "a3"] });
  });

  it("falls back to the label when the server sends no ability index", () => {
    const actions = [
      { ...activate("a1", 0, "{T}: Add {C}"), ability_index: null },
      { ...activate("a2", 0, "{T}: Add {R}"), ability_index: null },
    ];
    expect(abilitiesOf(actions, 7).map((a) => a.index)).toEqual([-1, -1]);
    expect(abilityRoute(actions, 7).kind).toBe("menu");
  });

  it("ignores other cards and other kinds", () => {
    const actions = [
      activate("a1", 0, "{T}: Add {C}"),
      { ...activate("a2", 0, "{T}: Add {C}"), source_oid: 8 },
      action({ id: "c1", kind: "cast", source_oid: 7 }),
    ];
    expect(abilityRoute(actions, 7)).toEqual({ kind: "act", id: "a1" });
  });
});

/**
 * A shock land's two land drops ask through the same menu.
 *
 * "As this land enters, you may pay 2 life. If you don't, it enters tapped."
 * The engine offers paying and declining as two land drops, each saying what
 * it does in `option_label`, so the hand press asks which -- the planeswalker's
 * dialog, not a targeting step with two chips nobody can see from the hand.
 */
describe("a land drop with a choice in it", () => {
  const drop = (id: string, option: string) =>
    action({
      id,
      kind: "play_land",
      label: `Play Blood Crypt (${option})`,
      base_label: "Play Blood Crypt",
      option_label: option,
      source_oid: 9,
    });

  it("is a menu of the two drops", () => {
    const route = abilityRoute([drop("p1", "Pay 2 life, untapped"), drop("p2", "Tapped")], 9);
    expect(route.kind).toBe("menu");
    if (route.kind !== "menu") return;
    expect(route.abilities.map((a) => a.text)).toEqual(["Pay 2 life, untapped", "Tapped"]);
    expect(route.abilities.map((a) => routeFor(a))).toEqual([
      { kind: "act", id: "p1" },
      { kind: "act", id: "p2" },
    ]);
  });

  it("leaves a plain land drop alone", () => {
    const plain = action({ id: "p1", kind: "play_land", label: "Play Forest", source_oid: 9 });
    expect(abilitiesOf([plain], 9)).toEqual([]);
  });
});

describe("a modal double-faced card in hand", () => {
  /*
   * Malakir Rebirth // Malakir Mire: the front is cast (one action per
   * target), the back is played as a land. Pressing the card has to ask which,
   * or the land half can never be chosen from the hand.
   */
  const cast = (id: string, target: number) =>
    action({
      id,
      kind: "cast",
      source_oid: 9,
      base_label: "Cast Malakir Rebirth // Malakir Mire",
      targets: [{ kind: "object", id: target }],
    });
  const land = action({
    id: "land",
    kind: "play_land",
    source_oid: 9,
    base_label: "Play Malakir Mire",
  });

  it("asks which face, the spell first", () => {
    const route = abilityRoute([land, cast("c1", 3), cast("c2", 4)], 9);
    expect(route.kind).toBe("menu");
    if (route.kind !== "menu") return;
    expect(route.abilities.map((a) => a.text)).toEqual([
      "Cast Malakir Rebirth",
      "Play Malakir Mire",
    ]);
    expect(route.abilities[0].ids).toEqual(["c1", "c2"]);
  });

  it("then targets with the spell and plays the land outright", () => {
    const route = abilityRoute([land, cast("c1", 3), cast("c2", 4)], 9);
    if (route.kind !== "menu") throw new Error("expected a menu");
    expect(routeFor(route.abilities[0])).toEqual({ kind: "target", ids: ["c1", "c2"] });
    expect(routeFor(route.abilities[1])).toEqual({ kind: "act", id: "land" });
  });

  it("is a plain cast when the land drop is spent", () => {
    expect(abilityRoute([cast("c1", 3)], 9)).toEqual({ kind: "none" });
  });
});
