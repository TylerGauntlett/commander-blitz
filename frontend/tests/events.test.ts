import { describe, expect, it } from "vitest";
import type { GameEvent } from "../src/api/types";
import { beatsFor, queueDuration } from "../src/logic/events";

const NAMES = ["You", "Edgar AI"];

function event(
  type: string,
  data: Record<string, unknown> = {},
  extra: Partial<GameEvent> = {},
): GameEvent {
  return { type, turn: 1, step: 3, player: 0, source: null, data, ...extra };
}

describe("beatsFor", () => {
  it("turns damage to a player into a floating numeral on that player", () => {
    const [beat] = beatsFor([event("damage_dealt", { amount: 4, to: "player" })], NAMES);
    expect(beat.float).toEqual({
      anchor: { kind: "player", pid: 0 },
      value: "-4",
      tone: "damage",
    });
  });

  it("anchors damage to a permanent on that permanent", () => {
    const [beat] = beatsFor(
      [event("damage_dealt", { amount: 2, to: "permanent", oid: 42 })],
      NAMES,
    );
    expect(beat.float?.anchor).toEqual({ kind: "object", oid: 42 });
  });

  it("shakes the screen only for big hits to a player", () => {
    const [big] = beatsFor([event("damage_dealt", { amount: 12, to: "player" })], NAMES);
    const [small] = beatsFor(
      [event("damage_dealt", { amount: 2, to: "permanent", oid: 1 })],
      NAMES,
    );
    expect(big.shake).toBeGreaterThan(0);
    expect(small.shake).toBeUndefined();
  });

  it("ignores zero and negative damage", () => {
    expect(beatsFor([event("damage_dealt", { amount: 0, to: "player" })], NAMES)).toEqual([]);
  });

  it("does not double-count combat damage to a player", () => {
    // damage_player fires damage_dealt *and* combat_damage_to_player for one hit.
    const beats = beatsFor(
      [
        event("damage_dealt", { amount: 3, to: "player" }),
        event("combat_damage_to_player", { amount: 3 }),
      ],
      NAMES,
    );
    expect(beats.filter((b) => b.float).length).toBe(1);
  });

  it("resolves card ids to printed names when a lookup is supplied", () => {
    const [beat] = beatsFor([event("spell_cast", { card: "sol_ring" })], NAMES, (id) =>
      id === "sol_ring" ? "Sol Ring" : undefined,
    );
    expect(beat.spotlight?.name).toBe("Sol Ring");
    expect(beat.text).toBe("You casts Sol Ring");
  });

  it("prettifies an unknown card id rather than showing the raw slug", () => {
    const [beat] = beatsFor([event("spell_cast", { card: "lightning_bolt" })], NAMES);
    expect(beat.spotlight?.name).toBe("Lightning Bolt");
  });

  it("banners the start of a turn", () => {
    const [beat] = beatsFor([event("turn_began", { turn: 3 }, { player: 1 })], NAMES);
    expect(beat.banner).toEqual({ text: "Edgar AI's Turn", tone: "neutral" });
  });

  it("banners an elimination and shakes", () => {
    const [beat] = beatsFor(
      [event("player_lost", { reason: "commander_damage" }, { player: 1 })],
      NAMES,
    );
    expect(beat.banner?.tone).toBe("danger");
    expect(beat.shake).toBeGreaterThan(0);
  });

  it("floats life gain up and life loss down", () => {
    const [gain] = beatsFor([event("life_gained", { amount: 5 })], NAMES);
    const [loss] = beatsFor([event("life_lost", { amount: 5 })], NAMES);
    expect(gain.float?.value).toBe("+5");
    expect(gain.float?.tone).toBe("gain");
    expect(loss.float?.value).toBe("-5");
  });

  it("flashes a permanent when it dies", () => {
    const [beat] = beatsFor([event("dies", { card: "bear" }, { source: 9 })], NAMES);
    expect(beat.flash).toEqual({ anchor: { kind: "object", oid: 9 }, tone: "danger" });
  });

  it("drops bookkeeping events entirely", () => {
    const noise = ["mana_added", "mana_spent", "mana_emptied", "zone_change", "step_ended"];
    expect(
      beatsFor(
        noise.map((type) => event(type)),
        NAMES,
      ),
    ).toEqual([]);
  });

  it("gives every beat a distinct id within a batch", () => {
    const beats = beatsFor([event("draw"), event("draw"), event("draw")], NAMES);
    expect(new Set(beats.map((b) => b.id)).size).toBe(3);
  });

  it("ignores event types it does not know", () => {
    expect(beatsFor([event("some_future_event")], NAMES)).toEqual([]);
  });
});

describe("queueDuration", () => {
  it("scales with the speed multiplier", () => {
    const beats = beatsFor([event("turn_began", { turn: 1 })], NAMES);
    expect(queueDuration(beats, 1)).toBe(850);
    expect(queueDuration(beats, 2)).toBe(425);
  });

  it("is zero for an empty queue", () => {
    expect(queueDuration([], 1)).toBe(0);
  });
});
