import { describe, expect, it } from "vitest";
import { targetHint, targetPhrases } from "../src/logic/targetHint";
import { action, card, gameView, player } from "./fixtures";

describe("targetPhrases", () => {
  it("quotes the target line and stops where the sentence moves on", () => {
    expect(targetPhrases("Destroy target creature. It can't be regenerated.")).toEqual([
      "target creature",
    ]);
    expect(targetPhrases("Return target creature to its owner's hand.")).toEqual([
      "target creature",
    ]);
    expect(targetPhrases("Target creature gets +3/+3 until end of turn.")).toEqual([
      "target creature",
    ]);
  });

  it("keeps a qualifier that is part of the target", () => {
    expect(
      targetPhrases("Destroy target nonland permanent with mana value 3 or less."),
    ).toEqual(["target nonland permanent with mana value 3 or less"]);
    expect(targetPhrases("Lightning Bolt deals 3 damage to any target.")).toEqual([
      "any target",
    ]);
  });

  it("reads each target of a two-target card, once", () => {
    expect(
      targetPhrases("Destroy target artifact and target land. Destroy target land."),
    ).toEqual(["target artifact", "target land"]);
  });

  it("ignores reminder text about being targeted", () => {
    expect(
      targetPhrases(
        "Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)",
      ),
    ).toEqual([]);
  });
});

describe("targetHint", () => {
  const murder = card({
    oid: 1,
    name: "Murder",
    zone: "hand",
    oracle_text: "Destroy target creature.",
  });
  const bear = card({ oid: 2, name: "Bear", types: ["Creature"] });
  const sigarda = card({ oid: 3, name: "Sigarda", types: ["Creature"], controller: 1 });
  const forest = card({ oid: 4, name: "Forest", types: ["Land"] });
  const state = gameView({
    battlefield: [bear, sigarda, forest],
    players: [player({ hand: [murder] }), player({ pid: 1 })],
  });
  const cast = action({
    id: "a1-cast",
    kind: "cast",
    base_label: "Cast Murder",
    source_oid: 1,
    targets: [{ kind: "object", id: 2 }],
    untargetable: { "3": "Hexproof" },
  });
  const targetable = new Set([2]);

  it("says nothing outside targeting, or with nothing hovered", () => {
    expect(targetHint(state, [], targetable, 2)).toBeNull();
    expect(targetHint(state, [cast], targetable, null)).toBeNull();
  });

  it("names a card the click would land on", () => {
    expect(targetHint(state, [cast], targetable, 2)).toEqual({
      text: "Target Bear",
      refused: false,
    });
  });

  it("gives the engine's reason for a card nothing may target", () => {
    expect(targetHint(state, [cast], targetable, 3)).toEqual({
      text: "Can't target Sigarda — Hexproof",
      refused: true,
    });
  });

  it("quotes the target line for a card the spell does not ask for", () => {
    expect(targetHint(state, [cast], targetable, 4)).toEqual({
      text: "Can't target Forest — Murder needs target creature",
      refused: true,
    });
  });

  it("falls back to the action's name when the text has no target line", () => {
    const blank = gameView({
      battlefield: [forest],
      players: [player({ hand: [{ ...murder, oracle_text: "" }] }), player({ pid: 1 })],
    });
    expect(targetHint(blank, [cast], targetable, 4)?.text).toBe(
      "Can't target Forest — not a legal target for Cast Murder",
    );
  });
});
