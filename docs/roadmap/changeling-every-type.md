---
id: changeling-every-type
title: Every creature type means every creature type
area: cards
effort: M
impact: medium
why: every changeling and Maskwood Nexus misses the tribe of the deck it is in, Squirrels, Rats and Wolves among them
depends_on: []
status: proposed
---

## Today

"Every creature type" is a closed list, `CHANGELING_SUBTYPES` in
`cards/authoring/templates.py`, whose comment says it holds every creature
type a shipped card mentions. It no longer does: Squirrel, Rat, Mouse,
Hamster, Raccoon and Wolf are all named by shipped cards and none is on it.
The changeling template copies the list into each card's `add_subtype`
static (`subtypes`), so every changeling card, every changeling token in
`data/cards/tokens.cards.json` and Maskwood Nexus's `off_battlefield` grant
carry their own frozen copy, and nothing checks that copy against the types
the pool actually reads.

So a changeling is not a Squirrel to Squirrel Sovereign or Chatterfang, nor
a Rat to Ogre Slumlord, and Maskwood Nexus does nothing for the Squirreled
Away deck it ships in. Each new tribe a precon brings widens the hole.

## The change

1. An `add_subtype` static can say `all_creature_types: true` instead of
   listing subtypes; `characteristics._compute`, the `off_battlefield` grant
   and the printed-type readers treat it as every creature type (205.3m)
   rather than a list, so a selector or trigger naming any creature type
   matches it.
2. The changeling template and the authoring packet emit the flag; the
   changeling cards, the changeling tokens and Maskwood Nexus move to it
   through `--collect` (tokens by hand under `/extend-dsl` Tier 0), and
   `CHANGELING_SUBTYPES` goes.
3. The loader refuses `all_creature_types` beside `subtypes`.

It does not change which creature types exist as words in the DSL, and it
leaves "choose a creature type" cards (`chosen_type_of`) as they are.

## Gate

A unit test under `tests/unit/statics/` that a changeling creature, a
changeling card in hand and a creature under Maskwood Nexus each match a
selector, a lord and a cast trigger naming Squirrel, Rat and a type no
shipped card names; the six gates over every changeling card; and the
golden pool re-pinned once.

## Open questions

- **A flag or a complete list.** A flag the engine reads as every type, or
  the full 205.3m list written into each card? Recommended: the flag, so the
  card data stops carrying a list that can go stale and a new tribe needs no
  re-authoring.
- **Is it an ADR.** Recommended: no; it restores what changeling (702.73) and
  the existing comment already promise, and its line goes in the "Type
  changes" row of rules-coverage.md.
