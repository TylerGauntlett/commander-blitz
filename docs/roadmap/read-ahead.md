---
id: read-ahead
title: Read ahead on Sagas (702.155)
area: cards
effort: S
impact: medium
why: every read-ahead Saga, The Elder Dragon War in Reign of Dragons among them, waits on it
depends_on: []
status: proposed
---

## Today

Sagas are rule 714 in `engine/sagas.py`: the lore counter a Saga enters with is
an enters replacement (714.2b), `sagas.entered` fires chapter I off it through
`chapters_reached` counted from zero, `turn_based_lore` adds one after the draw
step, and the sacrifice after the final chapter is a state-based action. Read
ahead is listed under "Not implemented" in
[rules-coverage.md](../rules-coverage.md): `Keyword` has no `READ_AHEAD`, no
card-level key lets the controller choose the starting lore count, and
`enters_with_additional_counters` is a fixed amount with no choice and no
suppression of the chapters it skips. The gap record
`data/authoring/gaps/the_elder_dragon_war.json` names this capability, and a
second need, the 4/4 red flying Dragon token its chapter III creates, which
`data/cards/tokens.cards.json` does not define (it has the 5/5 and the 6/6).

## The change

1. `Keyword.READ_AHEAD`, with its row in [keywords.md](../keywords.md) edited
   together with `engine/enums.py`. As a Saga with the keyword enters, its
   controller chooses a number from 1 to `final_chapter`, asked beside
   `offer_enters_costs` in `engine/zones.py` the way the other as-enters
   choices are, and the Saga enters with that many lore counters.
2. `sagas.entered` fires only the chosen chapter for that first placement
   (702.155: chapters below the chosen number do not trigger); every later
   tick goes through `chapters_reached` unchanged, and the sacrifice after the
   final chapter still applies.
3. The `dragon_4_4_r_flying` token, under `/extend-dsl` Tier 0.
4. Harvest The Elder Dragon War through `/author-cards`, then finish
   [precon-fdc-reign-of-dragons](precon-fdc-reign-of-dragons.md), which depends
   on this item.

It adds no double-lore effects, which stay under "Not implemented".

## Gate

A unit test under `tests/unit/` beside `test_saga.py` that enters a read-ahead
Saga at each chapter and asserts which chapter triggers and when it is
sacrificed; the token pinned in `tests/unit/tokens/test_token_pool.py`; the
keyword census test; and `tests/cards` with The Elder Dragon War through the
six gates.

## Decisions

- **Who answers the chapter choice when nobody is asked (the behaviour gate,
  a CPU):** chapter 1, the printed default for a Saga without the keyword, so
  the auto-answer table in `cards/authoring/verify.py` and the CPU strategies
  need no new reading of the board.
- **Scope of the pull request:** the keyword, the token and The Elder Dragon
  War only, titled `feat(cards):`; every other read-ahead Saga is left to the
  next `/author-cards` wave, so the review stays one mechanic.
