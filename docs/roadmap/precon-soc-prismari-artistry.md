---
id: precon-soc-prismari-artistry
title: Prismari Artistry (Secrets of Strixhaven Commander)
area: decks
effort: L
impact: high
why: a coming-soon tile on the shelf becomes a deck a player can pick
depends_on: [divided-damage-any-target]
status: proposed
rank: 9
---

## Today

Prismari Artistry, the Secrets of Strixhaven Commander precon released 2026-04-24, is a
coming-soon shell on the shelf: its row `soc_prismari_artistry` is in
`data/decks/sources.json` and there is no `data/decks/soc_prismari_artistry.deck.json`, so
`GET /api/precons/upcoming` serves it.
`python scripts/sync_precons.py --missing soc_prismari_artistry` lists the cards the engine
lacks, and the gap records in `data/authoring/gaps/` name the capability each
attempted card waits on.

Every card on the list has been through `/author-cards` once. What is left
is thirteen cards, each with a gap record naming what it waits on: Magma Opus
on divided damage that may hit players (its own item, which this one depends
on); Brazen Borrower on `can_block_only` and on its Adventure half, which the
card index does not carry; Plargg and Nassari on an exile-until walk; Surge to
Victory on an instant or sorcery prop in the sandbox graveyard; Muddle and
Twinflame on a copy that gains an ability as part of the copy; Abstract
Performance, Mirrorwing Dragon, Prismari Charm, Rootha, Mastering the Moment,
Rousing Refrain, Study Hall and Throes of Chaos on one capability each, named
in their records.

## The change

Prismari Artistry ships native, card for card, as one batch of
[every precon native](#every-precon-native-one-at-a-time-then-every-import), which holds the procedure:

1. `/author-cards` by name over the `--missing` list.
2. One `/extend-dsl` run per capability the gap records name, in the order
   the most cards elsewhere in the catalog wait on it.
3. Re-author until `--missing` is empty, then `--write-deck soc_prismari_artistry`, the
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

- **The Adventure half and the card index.** `scripts/build_card_index.py`
  keeps the `adventure` layout out of both `_HALVES_LAYOUTS` and
  `_TWO_FACED_LAYOUTS`, so Petty Theft is in no packet and no gate, and
  rebuilding `cards.sqlite` today pulls a newer Scryfall bundle that also moves
  every EDHREC rank and some oracle text. Does a precon batch refresh the
  catalog, or does that happen first as its own item? Recommended: its own
  item, adding `adventure` to the two-faced layouts and refreshing the index
  in one reviewable change, because the refresh touches cards far outside
  this deck and its oracle-text changes need their own look.
