---
id: precon-mkc-deadly-disguise
title: Deadly Disguise (Murders at Karlov Manor Commander)
area: decks
effort: L
impact: high
why: a coming-soon tile on the shelf becomes a deck a player can pick
depends_on: [changeling-every-type]
status: proposed
rank: 52
---

## Today

Deadly Disguise, the Murders at Karlov Manor Commander precon released 2024-02-09, is a
coming-soon shell on the shelf: its row `mkc_deadly_disguise` is in
`data/decks/sources.json` and there is no `data/decks/mkc_deadly_disguise.deck.json`, so
`GET /api/precons/upcoming` serves it.
`python scripts/sync_precons.py --missing mkc_deadly_disguise` lists the cards the engine
lacks, and the gap records in `data/authoring/gaps/` name the capability each
attempted card waits on.

Every card on the list has been through `/author-cards` once, and disguise,
`turn_face_up`, a face-down `return_from_graveyard`, counters on
`create_token` and the `deals_damage` trigger are built. Thirteen cards are
left, and each has a gap record naming what it waits on:

- Mirror Entity is every creature type, which
  [changeling-every-type](changeling-every-type.md) covers; this item
  depends on it.
- Boltbender needs "choose new targets" for spells and abilities already on
  the stack.
- Den Protector needs a block restriction comparing a blocker's power with
  this creature's.
- Duskana, the Rage Mother needs base power and toughness in a trigger
  filter.
- Hooded Hydra needs "as this is turned face up, put five +1/+1 counters on
  it", a replacement on turning face up.
- Kaust, Eyes of the Glade needs a "turned face up this turn" filter key.
- Obscuring Aether needs an op that turns a permanent face down and a
  face-down filter on spell cost reductions.
- Panoptic Projektor needs a next-spell discount for a face-down creature
  spell.
- Scroll of Fate needs manifest from hand.
- Tesak, Judith's Hellhound needs unleash.
- Veiled Ascension needs `face_down` in a static's `affects` filter.
- Yedora, Grave Gardener needs a face-down permanent that is a Forest land
  rather than a 2/2 creature.
- Zoetic Cavern needs morph on a land card.

## The change

Deadly Disguise ships native, card for card, as one batch of
[every precon native](#every-precon-native-one-at-a-time-then-every-import), which holds the procedure:

1. `/author-cards` by name over the `--missing` list.
2. One `/extend-dsl` run per capability the gap records name, in the order
   the most cards elsewhere in the catalog wait on it.
3. Re-author until `--missing` is empty, then `--write-deck mkc_deadly_disguise`, the
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
