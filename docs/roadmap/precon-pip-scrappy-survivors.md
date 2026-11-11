---
id: precon-pip-scrappy-survivors
title: Scrappy Survivors (Fallout)
area: decks
effort: L
impact: high
why: a coming-soon tile on the shelf becomes a deck a player can pick
depends_on: [rad-counters]
status: proposed
rank: 46
---

## Today

Scrappy Survivors, the Fallout precon released 2024-03-08, is a
coming-soon shell on the shelf: its row `pip_scrappy_survivors` is in
`data/decks/sources.json` and there is no `data/decks/pip_scrappy_survivors.deck.json`, so
`GET /api/precons/upcoming` serves it.
`python scripts/sync_precons.py --missing pip_scrappy_survivors` lists the cards the engine
lacks, and the gap records in `data/authoring/gaps/` name the capability each
attempted card waits on.

Every card on the list has been through `/author-cards` once. What is left
is fifteen cards, each with a gap record naming what it waits on: Acquired
Mutation and Megaton's Fate on rad counters (their own item, which this one
depends on); Codsworth, Handy Helper and Inventory Management on `attach`
checking an Aura's enchant clause; Cass, Hand of Vengeance on the Auras and
Equipment a dying creature had; Dogmeat, Ever Loyal on an "equipped" trigger
filter; Duchess, Wayward Tavernkeep on removing one named kind of counter as
a cost; Fertile Ground on an any-colour `add_mana_on_tap`; Gunner Conscript on
whether a dying creature was equipped; Moira Brown and Preston Garvey on the
Wasteland Survival Guide and Settlement tokens; Single Combat on a cast lock
by spell type until the end of your next turn; Three Dog on token copies of
an Aura entering attached; Vault 21: House Gambit on a shared-mana-value
selector; and Veronica, Dissident Scribe on a discard trigger for the first
time each turn.

## The change

Scrappy Survivors ships native, card for card, as one batch of
[every precon native](#every-precon-native-one-at-a-time-then-every-import), which holds the procedure:

1. `/author-cards` by name over the `--missing` list.
2. One `/extend-dsl` run per capability the gap records name, in the order
   the most cards elsewhere in the catalog wait on it.
3. Re-author until `--missing` is empty, then `--write-deck pip_scrappy_survivors`, the
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
