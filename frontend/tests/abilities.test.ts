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

  it("treats several untargeted variants of one ability as a choice, not a post", () => {
    // "Add one mana of any colour" is five actions that target nothing; the
    // panel's chips are where the colour is chosen.
    const actions = ["W", "U", "B"].map((c, i) => ({
      ...activate(`a${i}`, 0, "{T}: Add one mana of any color."),
      option_label: c,
    }));
    expect(abilityRoute(actions, 7)).toEqual({ kind: "target", ids: ["a0", "a1", "a2"] });
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
