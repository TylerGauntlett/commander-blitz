---
id: time-lord-subtype
title: Time Lord as one creature type
area: cards
effort: S
impact: medium
why: every Doctor Who card that names a Time Lord waits on it, Trenzalore Clocktower and Time Lord Regeneration in the Blast from the Past precon among them
depends_on: []
status: proposed
---

## Today

"Time Lord" is a single creature type (205.3m), the only one printed as two
words. `cards.proxy.split_type_line` splits the subtypes after the dash on
whitespace (`right.split()`), so every Time Lord the pool ships carries the two
subtypes `Time` and `Lord`: The Second, Third, Fifth and Thirteenth Doctor,
Romana II and The Master, Mesmerist. `SUBTYPE_CLASS` in `engine/enums.py`
knows neither word, so `characteristics` files both as creature types.

A selector naming the type, `{"subtypes": ["Time Lord"]}`, compiles and
matches nothing. So Trenzalore Clocktower's "Activate only if you control a
Time Lord" can never be met, and Time Lord Regeneration's "target Time Lord you
control" never has a target. Both cards are gapped under
`multiword_subtype_time_lord` (`data/authoring/gaps/trenzalore_clocktower.json`,
`data/authoring/gaps/time_lord_regeneration.json`), and TARDIS names a Time
Lord too. Naming `Time` or `Lord` alone would match the wrong things: `Lord`
is not a creature type, and a changeling would count twice.

## The change

1. `split_type_line` keeps a known multi-word subtype whole: a small table of
   the printed multi-word subtypes ("Time Lord"), joined before the split, so
   no whitelist of ordinary subtypes is needed.
2. `SUBTYPE_CLASS` learns `Time Lord` as a creature type, so changeling and
   `shares_a_creature_type_with` read it as one.
3. The six shipped Time Lords are re-collected through `--collect` with
   `["Time Lord", ...]` in place of `Time` and `Lord`, never hand-edited, and
   the golden pool and `registry_images.json` are re-pinned.
4. Trenzalore Clocktower and Time Lord Regeneration are authored again, in
   the same pull request, now that their selector matches.

It does not touch any other subtype.

## Gate

A unit test under `tests/unit/` that `split_type_line("Legendary Creature —
Time Lord Doctor")` yields `["Time Lord", "Doctor"]`, and that a permanent
with that type line matches `{"subtypes": ["Time Lord"]}` and not
`{"subtypes": ["Lord"]}`; `tests/cards` green over the re-collected cards, with
Trenzalore Clocktower's activated ability reached by the ability sandbox.

## Open questions

- **Where the joined name lives.** A table in `cards/proxy.py`, or a
  multi-word entry in `SUBTYPE_CLASS` that the splitter reads? Recommended: the
  splitter reads `SUBTYPE_CLASS`, so the engine's list of subtypes stays the
  one place a name is known.
- **Hand-written cards.** None print a Time Lord today; should the loader
  refuse `Time` and `Lord` as subtypes from now on, so a later card cannot
  bring the split back? Recommended: yes, a loader error naming "Time Lord".
