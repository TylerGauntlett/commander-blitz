/** Modal decisions about the hand: the London mulligan and discarding to hand size. */

import * as pool from "../cards";
import { action, gameView, pending } from "../fixtures";
import type { Scenario } from "./build";
import { opponent, you } from "./build";

/** The seven the opening-hand scenarios below all deal. */
function openingSeven() {
  return [
    pool.forest({ oid: 101, zone: "hand" }),
    pool.forest({ oid: 102, zone: "hand" }),
    pool.forest({ oid: 103, zone: "hand" }),
    pool.thragtusk({ oid: 104, zone: "hand" }),
    pool.serraAngel({ oid: 105, zone: "hand" }),
    pool.cultivate({ oid: 106, zone: "hand" }),
    pool.counterspell({ oid: 107, zone: "hand" }),
  ];
}

/**
 * The first half of a London mulligan: keep this hand, or take another seven.
 *
 * NEITHER OPTION CARRIES A CARD, and the comment that used to sit here claimed
 * the opposite. `engine/game.py` builds these two as bare
 * `DecisionOption(label=..., value=...)` with no `ref`, so `serialize._pending`
 * attaches no face and `PromptDialog.rowsFor` finds none -- which is exactly why
 * the one decision whose whole subject is a set of cards used to render as two
 * grey rectangles. `OpeningHand` does not read the options at all; it draws
 * `players[seat].hand`, which the server sends in full to the seat being asked.
 */
export function mulligan(taken = 0): Scenario {
  const hand = openingSeven();

  const state = gameView({
    step: "UNTAP",
    phase: "beginning",
    players: [{ ...you({ hand }), mulligans_taken: taken }, opponent(1, "AI 1")],
    pending: pending({ kind: "mulligan", prompt: "Keep this hand?" }),
  });

  return {
    state,
    actions: [
      action({ id: "a0-keep", kind: "keep", label: "Keep", base_label: "Keep" }),
      action({
        id: "a1-mulligan",
        kind: "mulligan",
        label: "Mulligan",
        base_label: "Mulligan",
      }),
    ],
    events: [],
  };
}

/**
 * The second half: two mulligans taken, the first free, so one card goes to
 * the bottom.
 *
 * A different decision KIND from the first half -- `choose_objects`, raised by
 * `ask_objects` -- and the only thing that tells it apart from every other
 * `choose_objects` is the `purpose` tag the engine stamps on it. That tag is why
 * `logic/openingHand.ts` never has to read the prompt string, and matching the
 * real payload here is the point of the fixture: these options DO carry refs and
 * faces, where the first half's carry neither.
 *
 * `bottom` is `min_count`, and the lamps show one more than that taken: a
 * London mulligan bottoms one card per mulligan, less the free one
 * (`FREE_MULLIGANS` in `engine/game.py`). `selected` is what the engine
 * has already banked, which is the half of this decision a single pick cannot
 * show: on two, the screen has to say how many are still wanted.
 */
export function mulliganBottom(bottom = 1, selected: number[] = []): Scenario {
  const hand = openingSeven();
  const state = gameView({
    step: "UNTAP",
    phase: "beginning",
    players: [
      { ...you({ hand }), mulligans_taken: bottom + 1 },
      { ...opponent(1, "AI 1"), mulligans_taken: 0 },
    ],
    pending: pending({
      kind: "choose_objects",
      prompt: `Put ${bottom} card(s) on the bottom of your library`,
      min_count: bottom,
      max_count: bottom,
      options: hand.map((c) => ({
        label: c.name,
        ref: { kind: "object", id: c.oid },
        value: c.oid,
        card: c,
      })),
      selected,
      context: { purpose: "mulligan_bottom", source_name: "Mulligan" },
    }),
  });

  return {
    state,
    /* Derived from the state, per this file's header: one action per option, in
       the same order, carrying the index the engine answers by. */
    actions: hand.map((c, i) =>
      action({
        id: `a${i}-bottom`,
        kind: "choose",
        label: c.name,
        base_label: c.name,
        choice: i,
        targets: [{ kind: "object", id: c.oid }],
      }),
    ),
    events: [],
  };
}

/** Over hand size at cleanup: choose two to pitch. */
export function discardToHandSize(): Scenario {
  const hand = [
    pool.forest({ oid: 101, zone: "hand" }),
    pool.island({ oid: 102, zone: "hand" }),
    pool.thragtusk({ oid: 103, zone: "hand" }),
    pool.serraAngel({ oid: 104, zone: "hand" }),
    pool.cultivate({ oid: 105, zone: "hand" }),
    pool.counterspell({ oid: 106, zone: "hand" }),
    pool.solRing({ oid: 107, zone: "hand" }),
    pool.rhysticStudy({ oid: 108, zone: "hand" }),
    pool.rancor({ oid: 109, zone: "hand" }),
  ];

  const state = gameView({
    step: "CLEANUP",
    phase: "ending",
    players: [you({ hand }), opponent(1, "AI 1")],
    pending: pending({
      kind: "discard_to_hand_size",
      prompt: "Discard down to seven cards",
      min_count: 2,
      max_count: 2,
    }),
  });

  return {
    state,
    actions: hand.map((c, i) =>
      action({
        id: `a${i}-choose`,
        kind: "choose",
        label: c.name,
        base_label: c.name,
        targets: [{ kind: "object", id: c.oid }],
      }),
    ),
    events: [],
  };
}
