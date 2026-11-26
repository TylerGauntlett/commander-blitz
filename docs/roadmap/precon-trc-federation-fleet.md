---
id: precon-trc-federation-fleet
title: Federation Fleet (Star Trek Commander)
area: decks
effort: M
impact: high
why: a coming-soon tile on the shelf becomes a deck a player can pick
depends_on: []
status: proposed
rank: 1
---

## Today

Federation Fleet, the Star Trek Commander precon released 2026-11-13, is a
coming-soon shell on the shelf: its row `trc_federation_fleet` is in
`data/decks/sources.json` and there is no `data/decks/trc_federation_fleet.deck.json`, so
`GET /api/precons/upcoming` serves it.
`python scripts/sync_precons.py --missing trc_federation_fleet` lists the cards the engine
lacks, and the gap records in `data/authoring/gaps/` name the capability each
attempted card waits on.

## The change

Federation Fleet ships native, card for card, as one batch of
[every precon native](#every-precon-native-one-at-a-time-then-every-import), which holds the procedure:

1. `/author-cards` by name over the `--missing` list.
2. One `/extend-dsl` run per capability the gap records name, in the order
   the most cards elsewhere in the catalog wait on it.
3. Re-author until `--missing` is empty, then `--write-deck trc_federation_fleet`, the
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

## Open questions

- **The set is newer than the card index.** `data/catalog/cards.sqlite` is
  built from a Scryfall bundle older than this precon (its `meta` table names
  the bundle), so of the cards `sync_precons.py --missing trc_federation_fleet`
  lists, only the reprints are in the catalog; for every new Star Trek card
  `author_cards.py --card` answers "no card named … in the catalog", and no
  packet, template or gate can reach it. **Today**'s claim that the pipeline
  can author the `--missing` list does not hold until the index is rebuilt.
  Does a precon batch rebuild the catalog (`build_card_index.py --refresh`)
  inside its own pull request, or does the refresh land first as its own item
  that every `precon-trc-*` item depends on? Recommended: its own item, a
  `chore(cards):` refresh of `cards.sqlite` and `registry_images.json` with the
  new art, added to the `depends_on` of all four `precon-trc-*` items, because
  a refresh moves every EDHREC rank and some oracle text across the whole
  catalog and deserves its own review; the same question is open on
  [precon-soc-prismari-artistry](precon-soc-prismari-artistry.md), and one
  answer can settle both.
