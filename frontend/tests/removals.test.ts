/**
 * Folding the event log into "how did this card get here".
 *
 * The durable half of the exit animation. Pure over the log, so it is provable
 * without a DOM -- which is the point of it living in `logic/` rather than
 * inside the modal that renders it.
 */

import { describe, expect, it } from "vitest";
import type { GameEvent } from "../src/api/types";
import { removalsByOid } from "../src/logic/removals";

function event(type: string, data: Record<string, unknown> = {}): GameEvent {
  return { type, turn: 1, step: 3, player: 0, source: null, data };
}

function left(oid: number, data: Record<string, unknown> = {}): GameEvent {
  return event("zone_change", {
    card: "grizzly_bears",
    oid,
    from: "battlefield",
    to: "graveyard",
    cause: "destroyed",
    ...data,
  });
}

describe("removalsByOid", () => {
  it("records why each card left, keyed by oid", () => {
    const notes = removalsByOid([
      left(4, { by_card: "vandalblast" }),
      left(9, { to: "exile", cause: "exiled" }),
    ]);
    expect(notes.get(4)).toBe("Destroyed by Vandalblast");
    expect(notes.get(9)).toBe("Exiled");
  });

  it("uses the printed name for the culprit when a lookup is given", () => {
    const notes = removalsByOid([left(4, { by_card: "swords_to_plowshares" })], (id) =>
      id === "swords_to_plowshares" ? "Swords to Plowshares" : undefined,
    );
    expect(notes.get(4)).toBe("Destroyed by Swords to Plowshares");
  });

  it("ignores everything that did not leave the battlefield", () => {
    // A drawn card was drawn -- no story worth telling. And a library-origin
    // zone change carries a card id to every seat, so folding one in would let
    // a player read an opponent's tutor out of their own graveyard modal.
    const notes = removalsByOid([
      event("zone_change", { oid: 1, from: "library", to: "hand", cause: "search" }),
      event("zone_change", { oid: 2, from: "stack", to: "graveyard", cause: "resolved" }),
      event("draw", { oid: 3 }),
    ]);
    expect(notes.size).toBe(0);
  });

  it("keeps the most recent departure", () => {
    // A creature can be bounced, recast and then destroyed. What put it where
    // the player is looking at it now is the last thing that happened to it.
    const notes = removalsByOid([
      left(4, { to: "hand", cause: "returned" }),
      left(4, { cause: "sacrificed", by_card: "ashnods_altar" }),
    ]);
    expect(notes.get(4)).toBe("Sacrificed to Ashnods Altar");
  });

  it("skips a zone change with no oid to key on", () => {
    // `op_put_on_top` emits one of these alongside the real move.
    expect(removalsByOid([event("zone_change", { to: "library_top" })]).size).toBe(0);
  });

  it("rebuilds from scratch, so an undo un-tells the story", () => {
    // `useGame` replaces the whole log on undo rather than appending, and this
    // holds no state between calls, so a rewound death simply stops appearing.
    const before = removalsByOid([left(4)]);
    const after = removalsByOid([]);
    expect(before.get(4)).toBeDefined();
    expect(after.get(4)).toBeUndefined();
  });
});
