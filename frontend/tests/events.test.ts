import { describe, expect, it } from "vitest";
import type { GameEvent } from "../src/api/types";
import type { Beat } from "../src/logic/beats/types";
import { beatsFor, queueDuration } from "../src/logic/events";
import { describeEvent } from "../src/logic/labels";

const NAMES = ["You", "Edgar AI"];

function event(
  type: string,
  data: Record<string, unknown> = {},
  extra: Partial<GameEvent> = {},
): GameEvent {
  return { type, turn: 1, step: 3, player: 0, source: null, data, ...extra };
}

/**
 * Damage moved out of `beat.float` and into `beat.fx`.
 *
 * Every `damage_dealt` is now collected by `logic/choreography.ts` into a run
 * and played as a concurrent burst -- sparks at the point of contact, a numeral
 * thrown off that same point, the victim knocked backwards -- so the numeral is
 * a scheduled effect rather than a property of the beat. These assert the same
 * facts through the new shape.
 */
function floats(beat: Beat | undefined) {
  return (beat?.fx ?? []).filter((fx) => fx.kind === "float");
}

function shakes(beat: Beat | undefined) {
  return (beat?.fx ?? []).filter((fx) => fx.kind === "shake");
}

describe("beatsFor", () => {
  it("turns damage to a player into a floating numeral on that player", () => {
    const [beat] = beatsFor([event("damage_dealt", { amount: 4, to: "player" })], NAMES);
    expect(floats(beat)).toMatchObject([
      { at_point: { kind: "player", pid: 0 }, value: "-4", tone: "damage" },
    ]);
  });

  it("anchors damage to a permanent on that permanent", () => {
    const [beat] = beatsFor(
      [event("damage_dealt", { amount: 2, to: "permanent", oid: 42 })],
      NAMES,
    );
    expect(floats(beat)[0]).toMatchObject({ at_point: { kind: "object", oid: 42 } });
  });

  it("throws sparks at whatever the damage landed on", () => {
    const [beat] = beatsFor(
      [event("damage_dealt", { amount: 2, to: "permanent", oid: 42 })],
      NAMES,
    );
    expect((beat.fx ?? []).filter((fx) => fx.kind === "emit")).toMatchObject([
      { preset: "impact", at_point: { kind: "object", oid: 42 } },
    ]);
  });

  it("shakes the screen only for big hits to a player", () => {
    const [big] = beatsFor([event("damage_dealt", { amount: 12, to: "player" })], NAMES);
    const [small] = beatsFor(
      [event("damage_dealt", { amount: 2, to: "permanent", oid: 1 })],
      NAMES,
    );
    expect(shakes(big).length).toBe(1);
    expect(shakes(small).length).toBe(0);
  });

  it("gives the per-creature combat damage summary no beat of its own", () => {
    // Every hit it summarises already has a beat; a second would sound the
    // combat twice.
    expect(beatsFor([event("creature_dealt_combat_damage", { amount: 3 })], NAMES)).toEqual([]);
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
    expect(beats.flatMap((b) => floats(b)).length).toBe(1);
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

  it("says when the turn is an extra one", () => {
    // An extra turn does not complete a round, so a plain "Your Turn" twice in
    // a row reads as the banner repeating itself.
    const [beat] = beatsFor(
      [event("turn_began", { turn: 4, extra: true }, { player: 0 })],
      NAMES,
      undefined,
      0,
    );
    expect(beat.banner).toEqual({ text: "Your Extra Turn", tone: "neutral" });
  });

  it("banners a skipped extra turn, from the viewer's side", () => {
    // `beatsFor` and `describeEvent` are parallel switches with parallel
    // `default`s. A skipped turn fires no `turn_began`, so without a beat of its
    // own the table simply moves on past the turn a spell promised.
    const [mine] = beatsFor(
      [event("turn_skipped", { extra: true }, { player: 0 })],
      NAMES,
      undefined,
      0,
    );
    const [theirs] = beatsFor(
      [event("turn_skipped", { extra: true }, { player: 1 })],
      NAMES,
      undefined,
      0,
    );
    expect(mine.banner).toEqual({ text: "You skip your extra turn", tone: "danger" });
    expect(theirs.banner).toEqual({ text: "Edgar AI skips their extra turn", tone: "good" });
  });

  it("banners an elimination and shakes", () => {
    const [beat] = beatsFor(
      [event("player_lost", { reason: "commander_damage" }, { player: 1 })],
      NAMES,
    );
    expect(beat.banner?.tone).toBe("danger");
    expect(beat.shake).toBeGreaterThan(0);
  });

  it("banners the monarch, from the viewer's side", () => {
    // `beatsFor` runs a switch parallel to `describeEvent` and both have a
    // `default` that drops what they do not know, which is how triggers once
    // went missing from both at once. A banner because nothing on the board
    // changed -- there is no permanent to flash and no number to float -- and
    // toned per seat, because gaining and losing the crown are one event told
    // two ways.
    const [mine] = beatsFor([event("became_monarch", {}, { player: 0 })], NAMES, undefined, 0);
    const [theirs] = beatsFor(
      [event("became_monarch", {}, { player: 1 })],
      NAMES,
      undefined,
      0,
    );
    expect(mine.banner).toEqual({ text: "You are the monarch", tone: "good" });
    expect(theirs.banner).toEqual({ text: "Edgar AI is the monarch", tone: "danger" });
  });

  it("gives a connive its own beat and line", () => {
    // Without a case here the connive would have a log line and no beat, and
    // the trigger that follows it would arrive with nothing before it.
    const [beat] = beatsFor(
      [event("connived", { card: "ultron_unlimited" }, { player: 1, source: 12 })],
      NAMES,
      undefined,
      0,
    );
    expect(beat).toMatchObject({ hold: 200 });
    expect(beat.text).toBe("Ultron Unlimited connives");
  });

  it("gives a library search its own beat and line", () => {
    // `beatsFor` and `describeEvent` are parallel switches with parallel
    // `default`s; a search left out of this one would be dropped from the
    // queue even with a log line, and it is the one moment of a tutor that
    // shows nothing on the board.
    const [beat] = beatsFor(
      [event("library_searched", { owner: 1 }, { player: 1, source: 12 })],
      NAMES,
      undefined,
      0,
    );
    expect(beat).toMatchObject({ hold: 260, sound: "shuffle" });
    expect(beat.text).toBe("Edgar AI searches their library");
  });

  it("banners an emblem, told from the viewer's side", () => {
    // Another table-level moment: the emblem sits in the command zone, which
    // is a pile, so there is nothing to flash. Neutral, because an emblem is as
    // often a curse handed to an opponent as a boon kept.
    const data = { card: "ob_nixilis_reignited" };
    const [mine] = beatsFor(
      [event("emblem_created", data, { source: 900 })],
      NAMES,
      undefined,
      0,
    );
    const [theirs] = beatsFor(
      [event("emblem_created", data, { player: 1, source: 900 })],
      NAMES,
      undefined,
      0,
    );
    expect(mine.banner).toEqual({ text: "You get an emblem", tone: "neutral" });
    expect(theirs.banner).toEqual({ text: "Edgar AI gets an emblem", tone: "neutral" });
    expect(theirs.text).toBe("Edgar AI gets an emblem from Ob Nixilis Reignited");
  });

  it("floats a Saga's chapter numeral off the Saga", () => {
    // `beatsFor` and `describeEvent` are parallel switches with parallel
    // `default`s, so a new event has to be added to both or it is dropped by
    // whichever was forgotten. A float rather than a banner because there *is* a
    // permanent and it is the one the eye should go to -- and worth a beat at all
    // because nothing on the board changes when a chapter triggers: the ability
    // goes on the stack and its tokens arrive a moment later, unannounced.
    const [beat] = beatsFor([event("chapter_reached", { chapter: 3 }, { source: 7 })], NAMES);
    expect(beat.float).toEqual({
      anchor: { kind: "object", oid: 7 },
      value: "III",
      tone: "good",
    });
  });

  it("floats a Class's new level off the Class", () => {
    // The same shape as a Saga's chapter: the level is not a counter, so no
    // counter beat floats beside it, and nothing else on the board says the
    // next band of abilities just switched on.
    const [beat] = beatsFor([event("became_level", { level: 2 }, { source: 7 })], NAMES);
    expect(beat.float).toEqual({
      anchor: { kind: "object", oid: 7 },
      value: "Level 2",
      tone: "good",
    });
  });

  it("floats life gain up and life loss down", () => {
    const [gain] = beatsFor([event("life_gained", { amount: 5 })], NAMES);
    const [loss] = beatsFor([event("life_lost", { amount: 5 })], NAMES);
    expect(gain.float?.value).toBe("+5");
    expect(gain.float?.tone).toBe("gain");
    expect(loss.float?.value).toBe("-5");
  });

  it("floats energy onto the player who got it", () => {
    const [beat] = beatsFor(
      [event("energy_added", { amount: 2, total: 5 })],
      NAMES,
      undefined,
      0,
    );
    expect(beat.float).toMatchObject({
      anchor: { kind: "player", pid: 0 },
      value: "+2 energy",
      tone: "gain",
    });
    expect(beat.text).toBe("You get 2 energy (5 total)");
  });

  it("floats energy spent off the player who paid it", () => {
    const [beat] = beatsFor(
      [event("energy_paid", { amount: 8, total: 1 })],
      NAMES,
      undefined,
      0,
    );
    expect(beat.float).toMatchObject({ value: "-8 energy", tone: "loss" });
    expect(beat.text).toBe("You pay 8 energy (1 left)");
  });

  it("drops bookkeeping events entirely", () => {
    // `mana_added` is not here even though payment is now narrated: it fires
    // once per source, and `tapped` already flashes the same permanent.
    // A bare `zone_change` with no `from` is still noise -- `op_put_on_top`
    // emits exactly one of those alongside the real move.
    const noise = ["mana_added", "mana_emptied", "zone_change", "step_ended", "untapped"];
    expect(
      beatsFor(
        noise.map((type) => event(type)),
        NAMES,
      ),
    ).toEqual([]);
  });

  describe("mana payment is visible", () => {
    it("flashes the permanent that taps to pay", () => {
      const [beat] = beatsFor([event("tapped", {}, { source: 12 })], NAMES);
      expect(beat.flash).toEqual({ anchor: { kind: "object", oid: 12 }, tone: "neutral" });
    });

    it("holds only briefly, because a big spell taps many sources at once", () => {
      const beats = beatsFor(
        [1, 2, 3, 4, 5].map((oid) => event("tapped", {}, { source: oid })),
        NAMES,
      );
      expect(beats).toHaveLength(5);
      expect(beats.reduce((sum, b) => sum + b.hold, 0)).toBeLessThan(600);
    });

    it("names what was spent", () => {
      const [beat] = beatsFor([event("mana_spent", { mana: "{2}{G}" })], NAMES);
      expect(beat.text).toBe("You pays {2}{G}");
    });
  });

  describe("triggered abilities", () => {
    it("gets a spotlight, like a cast does", () => {
      const [beat] = beatsFor(
        [event("ability_triggered", { card: "aesi" }, { source: 4 })],
        NAMES,
      );
      expect(beat.spotlight).toEqual({
        cardId: "aesi",
        name: "Aesi",
        controller: 0,
        kind: "trigger",
      });
    });

    it("flashes the source permanent so you can see where it came from", () => {
      const [beat] = beatsFor(
        [event("ability_triggered", { card: "aesi" }, { source: 4 })],
        NAMES,
      );
      expect(beat.flash).toEqual({ anchor: { kind: "object", oid: 4 }, tone: "good" });
    });

    it("is marked as a trigger, not a spell", () => {
      const [trigger] = beatsFor([event("ability_triggered", { card: "aesi" })], NAMES);
      const [cast] = beatsFor([event("spell_cast", { card: "aesi" })], NAMES);
      expect(trigger.spotlight?.kind).toBe("trigger");
      expect(cast.spotlight?.kind).toBeUndefined();
    });
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
    expect(queueDuration(beats, 1)).toBe(620);
    expect(queueDuration(beats, 2)).toBe(310);
  });

  it("is zero for an empty queue", () => {
    expect(queueDuration([], 1)).toBe(0);
  });
});

/**
 * Cards leaving the battlefield.
 *
 * The board used to simply stop drawing them: `dies` produced a flash anchored
 * to `[data-oid]`, and by the time a beat plays that element is unmounted, so
 * the one piece of feedback the code intended to give was dropped every time.
 * These beats carry enough to redraw the card from nothing.
 */
describe("exit beats", () => {
  const leaves = (
    oid: number,
    data: Record<string, unknown> = {},
    extra: Partial<GameEvent> = {},
  ) =>
    event(
      "zone_change",
      {
        card: "grizzly_bears",
        oid,
        from: "battlefield",
        to: "graveyard",
        cause: "destroyed",
        ...data,
      },
      extra,
    );

  it("describes a departure well enough to draw it", () => {
    const [beat] = beatsFor([leaves(4, { by_card: "vandalblast" })], NAMES, undefined, 0);
    expect(beat.exits).toEqual([
      {
        oid: 4,
        cardId: "grizzly_bears",
        name: "Grizzly Bears",
        owner: 0,
        to: "graveyard",
        cause: "destroyed",
        caption: "Destroyed by Vandalblast",
      },
    ]);
  });

  it("ignores a zone change that did not start on the battlefield", () => {
    // No card on screen to fly anywhere -- and a library-origin zone change
    // carries a card id to every seat, so drawing one would show the table an
    // opponent's tutor target.
    const events = [
      leaves(4, { from: "library", to: "hand", cause: "search" }),
      leaves(5, { from: "stack", to: "graveyard", cause: "resolved" }),
    ];
    expect(beatsFor(events, NAMES).flatMap((b) => b.exits ?? [])).toEqual([]);
  });

  it("ignores a zone change with no oid to anchor", () => {
    expect(beatsFor([leaves(4, { oid: undefined })], NAMES)).toEqual([]);
  });

  it("collapses a wrath into one beat", () => {
    // Five beats at a readable single-death pace is six seconds of stalled
    // board. The FX layer staggers the ghosts inside the one beat instead.
    const wrath = [0, 1, 2, 3, 4].map((oid) => leaves(oid));
    const beats = beatsFor(wrath, NAMES, undefined, 0);
    expect(beats).toHaveLength(1);
    expect(beats[0].exits).toHaveLength(5);
    expect(beats[0].text).toBe("5 permanents leave the battlefield");
  });

  it("keeps a run open across the silent events a death fires alongside it", () => {
    // `move_object` fires `dies` and `leaves_battlefield` between each pair of
    // zone changes. If those broke the run, no wrath would ever group.
    const wrath = [
      leaves(0),
      event("leaves_battlefield", { card: "grizzly_bears" }),
      event("dies", { card: "grizzly_bears" }),
      leaves(1),
      event("dies", { card: "grizzly_bears" }),
    ];
    expect(beatsFor(wrath, NAMES).filter((b) => b.exits)).toHaveLength(1);
  });

  it("splits a run at anything that would itself be narrated", () => {
    // Ordering is the point: a death, the trigger it caused, then a second
    // death is three moments, and merging the deaths would put the second on
    // screen before its cause.
    const beats = beatsFor(
      [leaves(0), event("ability_triggered", { card: "blood_artist" }), leaves(1)],
      NAMES,
    );
    expect(beats.filter((b) => b.exits)).toHaveLength(2);
  });

  it("holds sublinearly, so a wide board wipe does not stall the turn", () => {
    const hold = (n: number) =>
      beatsFor(
        Array.from({ length: n }, (_, i) => leaves(i)),
        NAMES,
      )[0].hold;
    expect(hold(1)).toBe(420);
    expect(hold(10)).toBeLessThanOrEqual(820);
    expect(hold(10)).toBeGreaterThan(hold(1));
  });

  it("tolls for the graveyard and exile, and not for a bounce", () => {
    expect(beatsFor([leaves(4)], NAMES)[0].sound).toBe("toll");
    expect(beatsFor([leaves(4, { to: "exile", cause: "exiled" })], NAMES)[0].sound).toBe(
      "toll",
    );
    const bounced = leaves(4, { to: "hand", cause: "returned" });
    expect(beatsFor([bounced], NAMES)[0].sound).toBeUndefined();
  });

  it("shakes the screen for a wipe but not for a single death", () => {
    expect(beatsFor([leaves(0)], NAMES)[0].shake).toBeUndefined();
    const wrath = [0, 1, 2, 3, 4, 5].map((oid) => leaves(oid));
    expect(beatsFor(wrath, NAMES)[0].shake).toBeGreaterThan(0);
  });

  it("flies to the zone the engine used, not the one the cause implies", () => {
    // Rule 903.9a: a destroyed commander goes to the command zone. Deriving the
    // destination from `cause` would send the ghost to a graveyard it is not in.
    const [beat] = beatsFor([leaves(4, { to: "command" })], NAMES, undefined, 0);
    expect(beat.exits?.[0].to).toBe("command");
    expect(beat.exits?.[0].caption).toBe("Destroyed — to the command zone");
  });

  it("no longer narrates `dies`, which would double every death", () => {
    expect(beatsFor([event("dies", { card: "grizzly_bears" }, { source: 9 })], NAMES)).toEqual(
      [],
    );
  });
});

/**
 * One switch owns the words.
 *
 * `beatsFor` used to carry its own prose, parallel to `describeEvent` and over
 * the same event types. That is how triggers came to be missing from both at
 * once, and why payment narrated "You pays {2}{G}" while the log beside it said
 * "You pay". These tests pin the two together, so the next event kind cannot be
 * given a line in one place and forgotten in the other.
 */
describe("beat text comes from describeEvent", () => {
  const cases: GameEvent[] = [
    event("turn_began", { turn: 3, round: 2 }),
    event("turn_began", { turn: 4, round: 2, extra: true }),
    event("turn_skipped", { extra: true }),
    event("spell_cast", { card: "sol_ring" }),
    event("land_played", { card: "forest" }),
    event("ability_triggered", { card: "scoured_barrens" }),
    event("mana_spent", { mana: "{2}{G}" }),
    event("damage_dealt", { amount: 3, to: "player" }),
    event("life_gained", { amount: 2 }),
    event("energy_added", { amount: 2, total: 2 }),
    event("energy_paid", { amount: 2, total: 0 }),
    event("draw"),
    event("zone_change", {
      card: "t_bear",
      oid: 4,
      from: "battlefield",
      to: "graveyard",
      cause: "destroyed",
    }),
    event("player_lost", { reason: "life" }),
  ];

  it.each(cases.map((e) => [e.type, e] as const))(
    "%s reads the same in the log and in the narration",
    (_type, raw) => {
      const [beat] = beatsFor([raw], NAMES, undefined, 0);
      expect(beat.text).toBe(describeEvent(raw, NAMES, 0));
    },
  );

  it("agrees for every event the queue will narrate", () => {
    // The whole contract in one, across a realistic batch rather than a list of
    // hand-picked types.
    const beats = beatsFor(cases, NAMES, undefined, 0);
    const lines = cases
      .map((raw) => describeEvent(raw, NAMES, 0))
      .filter((line) => line !== null);
    expect(beats.map((b) => b.text).filter((t) => t !== null)).toEqual(lines);
  });

  it("uses the printed name when a lookup is given", () => {
    const lookup = (id: string) => (id === "sol_ring" ? "Sol Ring" : undefined);
    const [beat] = beatsFor([event("spell_cast", { card: "sol_ring" })], NAMES, lookup, 0);
    expect(beat.text).toContain("Sol Ring");
  });
});

describe("verb agreement", () => {
  it("says 'you pay' rather than 'You pays'", () => {
    // The bug the duplication caused: `beatsFor` had no notion of the viewer at
    // all, so every line it wrote used the third-person verb.
    const [beat] = beatsFor([event("mana_spent", { mana: "{2}{G}" })], NAMES, undefined, 0);
    expect(beat.text).toBe("You pay {2}{G}");
  });

  it("keeps the third person for everybody else", () => {
    const raw = event("mana_spent", { mana: "{2}{G}" }, { player: 1 });
    const [beat] = beatsFor([raw], NAMES, undefined, 0);
    expect(beat.text).toBe("Edgar AI pays {2}{G}");
  });

  it("agrees on the events that make up most of a log", () => {
    for (const type of ["draw", "land_played", "spell_cast", "attackers_declared"]) {
      const [beat] = beatsFor([event(type, { card: "forest" })], NAMES, undefined, 0);
      // "You draws", "You plays", "You casts" -- a third-person verb after
      // the second-person pronoun, which is what a missing viewerSeat gave.
      expect(beat.text, `${type} disagrees with "you"`).not.toMatch(/^You \w+s(\s|$)/);
    }
  });
});

describe("beats still own timing and effects", () => {
  it("keeps the hold, sound and spotlight that describeEvent knows nothing about", () => {
    const [beat] = beatsFor([event("spell_cast", { card: "sol_ring" })], NAMES, undefined, 0);
    expect(beat.hold).toBeGreaterThan(0);
    expect(beat.sound).toBe("chime");
    expect(beat.spotlight?.cardId).toBe("sol_ring");
  });

  it("keeps banner text, which is a label rather than play-by-play", () => {
    const raw = event("turn_began", { round: 2 }, { player: 1 });
    const [beat] = beatsFor([raw], NAMES, undefined, 0);
    expect(beat.banner?.text).toBe("Edgar AI's Turn");
  });

  it("says 'Your Turn' rather than \"You's Turn\"", () => {
    // The viewer's name is literally "You", so every possessive built by
    // sticking an apostrophe-s on it came out wrong.
    const [beat] = beatsFor([event("turn_began", { round: 2 })], NAMES, undefined, 0);
    expect(beat.banner?.text).toBe("Your Turn");
    expect(beat.text).toBe("-- Your turn 2 --");
  });

  it("narrates the round, not the engine's player-turn counter", () => {
    const [beat] = beatsFor([event("turn_began", { turn: 5, round: 3 })], NAMES, undefined, 0);
    expect(beat.text).toContain("turn 3");
    expect(beat.text).not.toContain("turn 5");
  });
});
