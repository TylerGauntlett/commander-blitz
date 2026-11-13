---
id: precon-pip-science
title: Science! (Fallout)
area: decks
effort: L
impact: high
why: a coming-soon tile on the shelf becomes a deck a player can pick
depends_on: [secret-choices]
status: proposed
rank: 47
---

## Today

Science!, the Fallout precon released 2024-03-08, is a
coming-soon shell on the shelf: its row `pip_science` is in
`data/decks/sources.json` and there is no `data/decks/pip_science.deck.json`, so
`GET /api/precons/upcoming` serves it.
`python scripts/sync_precons.py --missing pip_science` lists the cards the engine
lacks, and the gap records in `data/authoring/gaps/` name the capability each
attempted card waits on.

Every card on the list has been through `/author-cards` once. Twenty cards
are left, and each has a gap record naming what it waits on:

- Expert-Level Safe needs secret choices, which have
  [their own item](secret-choices.md); this item depends on it.
- Automated Assembly Line needs the 3/3 Robot artifact creature token, and
  The Prydwen, Steel Flagship needs its Human Knight token.
- Arcade Gannon needs a graveyard-cast permission capped by a counted mana
  value.
- Bottle-Cap Blast needs the excess damage a spell dealt.
- Brotherhood Scribe needs a trigger for getting energy, and HELIOS One needs
  paying X energy as a cost.
- C.A.M.P. needs a trigger for a permanent being tapped for mana, with the
  colour it produced.
- Curie, Emergent Intelligence needs exiling a permanent as a cost and its
  base power.
- James, Wandering Dad needs its Adventure half, which the catalog row
  carries no text for.
- Mechanized Production needs an artifact you control in the authoring
  sandbox.
- Mystic Forge needs `colorless` in `cast_from_library_top`'s spell filter.
- Nerd Rage needs a granted ability that carries a player-wide static.
- Plasma Caster needs a "creature blocking equipped creature" target.
- Rex, Cyber-Hound needs the activated abilities of exiled cards chosen by
  their counters.
- Sentry Bot needs a cost reduction counted per attacking player.
- Synth Infiltrator needs `add_subtypes` on an enters-as-a-copy.
- The Motherlode, Excavator needs a can't-block over a filtered group,
  checked at declare blockers.
- Vault 13: Dweller's Journey needs a choice among the cards a permanent
  exiled.
- Vault 112: Sadistic Simulation needs to play an exiled land during
  resolution.

## The change

Science! ships native, card for card, as one batch of
[every precon native](#every-precon-native-one-at-a-time-then-every-import), which holds the procedure:

1. `/author-cards` by name over the `--missing` list.
2. One `/extend-dsl` run per capability the gap records name, in the order
   the most cards elsewhere in the catalog wait on it.
3. Re-author until `--missing` is empty, then `--write-deck pip_science`, the
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
