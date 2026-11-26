---
id: precon-ltc-the-hosts-of-mordor
title: The Hosts of Mordor (Tales of Middle-earth Commander)
area: decks
effort: L
impact: high
why: a coming-soon tile on the shelf becomes a deck a player can pick
depends_on: [the-ring-tempts-you]
status: proposed
rank: 37
---

## Today

The Hosts of Mordor, the Tales of Middle-earth Commander precon released 2023-06-23, is a
coming-soon shell on the shelf: its row `ltc_the_hosts_of_mordor` is in
`data/decks/sources.json` and there is no `data/decks/ltc_the_hosts_of_mordor.deck.json`, so
`GET /api/precons/upcoming` serves it.
`python scripts/sync_precons.py --missing ltc_the_hosts_of_mordor` lists the cards the engine
lacks, and the gap records in `data/authoring/gaps/` name the capability each
attempted card waits on.
One of those capabilities is a rules subsystem the engine does not have
([rules-coverage.md](../rules-coverage.md#not-implemented)). The deck's
commander, Sauron, Lord of the Rings, has the Ring tempt you whenever an
opponent's commander dies, and Fiery Inscription, In the Darkness Bind Them and
Lord of the Nazgûl tempt you too, so the deck waits on
[the Ring](the-ring-tempts-you.md). The rest of its missing cards wait on
tokens and smaller capabilities this batch builds once the Ring lands.

## The change

The Hosts of Mordor ships native, card for card, as one batch of
[every precon native](#every-precon-native-one-at-a-time-then-every-import), which holds the procedure:

1. `/author-cards` by name over the `--missing` list.
2. One `/extend-dsl` run per capability the gap records name, in the order
   the most cards elsewhere in the catalog wait on it.
3. Re-author until `--missing` is empty, then `--write-deck ltc_the_hosts_of_mordor`, the
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
