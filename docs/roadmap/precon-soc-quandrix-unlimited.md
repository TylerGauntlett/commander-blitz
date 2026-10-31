---
id: precon-soc-quandrix-unlimited
title: Quandrix Unlimited (Secrets of Strixhaven Commander)
area: decks
effort: L
impact: high
why: a coming-soon tile on the shelf becomes a deck a player can pick
depends_on: [distributed-counters-on-spells]
status: proposed
rank: 13
---

## Today

Quandrix Unlimited, the Secrets of Strixhaven Commander precon released 2026-04-24, is a
coming-soon shell on the shelf: its row `soc_quandrix_unlimited` is in
`data/decks/sources.json` and there is no `data/decks/soc_quandrix_unlimited.deck.json`, so
`GET /api/precons/upcoming` serves it.
`python scripts/sync_precons.py --missing soc_quandrix_unlimited` lists the cards the engine
lacks, and the gap records in `data/authoring/gaps/` name the capability each
attempted card waits on.

Every card on the list has been through `/author-cards` once. What is left
is twenty-one cards, each with a gap record naming what it waits on: Elusive
Otter on distributing counters from a spell (Grove's Bounty, its Adventure
half; its own item, which this one depends on) and on a block restriction by
relative power; Lattice Library, Nev, the Practical Dean, Owlin
Spiralmancer, Unbound Flourishing and Zimone, Infinite Analyst on a
`spell_cast` trigger filter for {X} in the spell's mana cost; Hydroid Krasis
and Nev on a cast trigger reading the spell's X; Altered Ego, Elementalist's
Palette, Entrancing Melody, Forgotten Ancient, Nexus Mentality, Opal Palace,
Open the Way, Oversimplify, Primo, the Unbounded, Quandrix Command,
Stonecoil Serpent, Yavimaya Bloomsage, Zimone, All-Questioning and Zimone's
Hypothesis on one or two capabilities each, named in their records.

## The change

Quandrix Unlimited ships native, card for card, as one batch of
[every precon native](#every-precon-native-one-at-a-time-then-every-import), which holds the procedure:

1. `/author-cards` by name over the `--missing` list.
2. One `/extend-dsl` run per capability the gap records name, in the order
   the most cards elsewhere in the catalog wait on it.
3. Re-author until `--missing` is empty, then `--write-deck soc_quandrix_unlimited`, the
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
