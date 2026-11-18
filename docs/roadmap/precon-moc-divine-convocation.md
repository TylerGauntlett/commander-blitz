---
id: precon-moc-divine-convocation
title: Divine Convocation (March of the Machine Commander)
area: decks
effort: L
impact: high
why: a coming-soon tile on the shelf becomes a deck a player can pick
depends_on: [planechase]
status: proposed
rank: 68
---

## Today

Divine Convocation, the March of the Machine Commander precon released 2023-04-21, is a
coming-soon shell on the shelf: its row `moc_divine_convocation` is in
`data/decks/sources.json` and there is no `data/decks/moc_divine_convocation.deck.json`, so
`GET /api/precons/upcoming` serves it.
`python scripts/sync_precons.py --missing moc_divine_convocation` lists the cards the engine
lacks, and the gap records in `data/authoring/gaps/` name the capability each
attempted card waits on.
One of those capabilities is a rules subsystem the engine does not have:
Fractured Powerstone rolls the planar die, Ichor Elixir replaces planar die
rolls, and Path of the Ghosthunter has the players vote to planeswalk or make
chaos ensue, so the deck waits on [Planechase](planechase.md). The rest of its
missing cards wait on smaller capabilities this batch builds once Planechase
lands, `convoke` above all (Flockchaser Phantom, Joyful Stormsculptor, Kasla,
the Broken Halo, Saint Traft and Rem Karolus, Venerated Loxodon, Wand of the
Worldsoul), then three tokens (The Locust God, Saint Traft and Rem Karolus,
Wildfire Awakener), Path of the Ghosthunter's `voting`, and one card each for
`prevent-damage-by-source`, `prevent_next_n_damage_divided`,
`flashback-nonmana-cost`, `activated_this_turn` and `sandbox_combat_targets`.

## The change

Divine Convocation ships native, card for card, as one batch of
[every precon native](#every-precon-native-one-at-a-time-then-every-import), which holds the procedure:

1. `/author-cards` by name over the `--missing` list.
2. One `/extend-dsl` run per capability the gap records name, in the order
   the most cards elsewhere in the catalog wait on it.
3. Re-author until `--missing` is empty, then `--write-deck moc_divine_convocation`, the
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
