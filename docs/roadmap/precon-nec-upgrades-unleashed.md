---
id: precon-nec-upgrades-unleashed
title: Upgrades Unleashed (Neon Dynasty Commander)
area: decks
effort: L
impact: high
why: a coming-soon tile on the shelf becomes a deck a player can pick
depends_on: []
status: proposed
rank: 54
---

## Today

Upgrades Unleashed, the Neon Dynasty Commander precon released 2022-02-18, is a
coming-soon shell on the shelf: its row `nec_upgrades_unleashed` is in
`data/decks/sources.json` and there is no `data/decks/nec_upgrades_unleashed.deck.json`, so
`GET /api/precons/upcoming` serves it.
Every card on its list is native: `python scripts/sync_precons.py --missing
nec_upgrades_unleashed` prints nothing. What stops `--write-deck` from shipping
is the list itself: the published list its `source` names carries
**Mossfire Valley twice** in its 99, so the deck file it writes fails
`tests/cards/test_deck_legality.py` (a nonbasic land over its copy limit of
one, 903.5b), and `sync_precons.py` has no per-precon correction to apply.

## The change

Upgrades Unleashed ships native, card for card, as one batch of
[every precon native](#every-precon-native-one-at-a-time-then-every-import), which holds the procedure:

1. `/author-cards` by name over the `--missing` list.
2. One `/extend-dsl` run per capability the gap records name, in the order
   the most cards elsewhere in the catalog wait on it.
3. Re-author until `--missing` is empty, then `--write-deck nec_upgrades_unleashed`, the
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

- **The doubled Mossfire Valley.** The published list carries two copies of a
  nonbasic land, which no legal Commander deck may (903.5b), and the run will
  not ship a deck that fails `test_deck_legality.py` or loosen that test. Which
  list ships? Recommended: check Wizards' own decklist for the product; if it
  prints one Mossfire Valley, the second copy is a source error and the run
  puts the card Wizards lists in its place. If the product really shipped two,
  replace the second with a basic Mountain, since Chishiro's deck is
  Gruul and a basic is the one change that alters no card's interaction. Either
  way the correction lives in `data/decks/sources.json` as a per-row override
  `sync_precons.py --write-deck` applies, so a re-sync cannot bring the
  duplicate back, and the deck's `notes` say what was changed and why.
