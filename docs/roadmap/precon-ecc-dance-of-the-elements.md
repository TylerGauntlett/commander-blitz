---
id: precon-ecc-dance-of-the-elements
title: Dance of the Elements (Lorwyn Eclipsed Commander)
area: decks
effort: L
impact: high
why: a coming-soon tile on the shelf becomes a deck a player can pick
depends_on: [divided-damage-on-abilities]
status: proposed
rank: 15
---

## Today

Dance of the Elements, the Lorwyn Eclipsed Commander precon released 2026-01-23, is a
coming-soon shell on the shelf: its row `ecc_dance_of_the_elements` is in
`data/decks/sources.json` and there is no `data/decks/ecc_dance_of_the_elements.deck.json`, so
`GET /api/precons/upcoming` serves it.
`python scripts/sync_precons.py --missing ecc_dance_of_the_elements` lists the cards the engine
lacks, and the gap records in `data/authoring/gaps/` name the capability each
attempted card waits on.

Every card on the list has been through `/author-cards` once. What is left
is eleven cards, each with a gap record naming what it waits on: Fury on
divided damage from a triggered ability (its own item, which this one
depends on); Ashling, the Limitless on granting evoke to Elemental spells by a
static; Endurance on putting cards on the bottom of a library in a random
order; Fertile Ground on an any-colour `add_mana_on_tap`; Flamekin Village on a
cost that reveals a card from hand, the same sentence Primal Beyond reads
loosely today as an unconditional enters-tapped, as the shipped reveal-lands
do; Haunting Voyage on a `foretold` condition; Impulsivity on a free cast from a
graveyard that exiles instead; Jegantha, the Wellspring on its companion line
(inert inside a game, 702.139a) and mana that cannot pay generic costs; Mass of
Mysteries on myriad; Muldrotha, the Gravetide on a graveyard cast metered per
permanent type; and Opal Palace on mana that makes a commander enter with
counters.

## The change

Dance of the Elements ships native, card for card, as one batch of
[every precon native](#every-precon-native-one-at-a-time-then-every-import), which holds the procedure:

1. `/author-cards` by name over the `--missing` list.
2. One `/extend-dsl` run per capability the gap records name, in the order
   the most cards elsewhere in the catalog wait on it.
3. Re-author until `--missing` is empty, then `--write-deck ecc_dance_of_the_elements`, the
   dossier and the archetype, and the deck joins `PRECONS` in
   `tests/cards/test_deck_legality.py`; its shell leaves the shelf by itself.
4. One `/author-cards` wave over the pending cards the new capabilities reach.

It does not touch another precon's deck.

## Gate

`tests/cards/test_precon_imports.py` over the new deck; one unit test under
`tests/unit/` per capability; the manifest test and
`tests/server/test_upcoming_precons.py` still green; and the sampled
whole-game test able to draw the deck.

## Decisions

- **Scope:** this precon only, taken to 100% in one pull request titled
  `feat(cards):`; the harvest is one `/author-cards` wave and no more.
- **The editorial fields:** the run writes the dossier and picks the closest
  existing `archetype`. It adds no strategy module or `docs/cpus/` page; an
  archetype that visibly misplays the deck is a new item.
- **A capability that needs a rules subsystem the engine does not have**
  (`rules-coverage.md`, not implemented): the run stops there, writes it as its
  own item through `/plan-feature`, adds it to this item's `depends_on`, sets
  this item back to `proposed`, and opens the pull request with the cards and
  capabilities done so far. This item stays until the deck is whole.
