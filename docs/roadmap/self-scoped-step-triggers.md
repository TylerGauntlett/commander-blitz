---
id: self-scoped-step-triggers
title: A step trigger scoped to its own permanent fires
area: cards
effort: S
impact: medium
why: Mystic Remora, Darksteel Reactor and Krosan Cloudscraper never ask for their upkeep, so each plays as a different card
depends_on: []
status: proposed
---

## Today

`triggers._matches` drops a trigger whose spec says `source: "self"` unless
the event's subject (`_subject_oid`) or its `source` is the permanent holding
the ability. A step event such as `upkeep` has neither: it is about a player,
not an object. So an `upkeep` trigger written with `source: "self"` never
fires, whatever its condition says.

Three shipped cards in `data/cards/auto/templates.cards.json` carry that
shape: Mystic Remora's cumulative upkeep, Darksteel Reactor's charge counter
and Krosan Cloudscraper's cumulative upkeep. Each therefore plays as a
stronger card than the printed one, with its upkeep cost never asked. The
authoring gates cannot see it, because the sandbox never reaches an upkeep
(`cards/authoring/verify.py`), so every expectation passes on a trigger
that is dead. The echo work found it: `tests/unit/keywords/test_echo.py`
writes its upkeep trigger without `source` for this reason.

## The change

1. Decide where the fix lives (see **Open questions**), and make it there.
2. If the engine keeps refusing the shape, the loader refuses it too, so a
   new card cannot ship it: `source: "self"` on a trigger event that has no
   subject object is a load error naming the event.
3. Re-author or correct the three cards so their upkeep triggers fire, and
   re-pin the golden pool.

It does not change what `source: "self"` means on any event that has a
subject.

## Gate

A unit test under `tests/unit/triggers/` that steps each of the three
shipped cards into its controller's upkeep and asserts the trigger goes on
the stack, plus a loader test for whichever refusal step 2 adds;
`tests/cards` stays green.

## Open questions

- **Engine or data?** Either `_matches` treats `source: "self"` as satisfied
  on a step event (a permanent's own "at the beginning of your upkeep" is
  scoped to it by being on the battlefield), or the three cards drop
  `source` and the loader refuses it on step events. Recommended: the
  loader refusal plus the data fix, because it keeps one meaning for
  `source: "self"` (this object is the event's subject) and makes the
  mistake impossible to ship again.
