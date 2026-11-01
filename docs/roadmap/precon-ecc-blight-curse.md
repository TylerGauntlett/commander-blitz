---
id: precon-ecc-blight-curse
title: Blight Curse (Lorwyn Eclipsed Commander)
area: decks
effort: L
impact: high
why: a coming-soon tile on the shelf becomes a deck a player can pick
depends_on: []
status: proposed
rank: 14
---

## Today

Blight Curse, the Lorwyn Eclipsed Commander precon released 2026-01-23, is a
coming-soon shell on the shelf: its row `ecc_blight_curse` is in
`data/decks/sources.json` and there is no `data/decks/ecc_blight_curse.deck.json`, so
`GET /api/precons/upcoming` serves it.
`python scripts/sync_precons.py --missing ecc_blight_curse` lists the cards the engine
lacks, and the gap records in `data/authoring/gaps/` name the capability each
attempted card waits on.

Every card on the list has been through `/author-cards`, and the capabilities
its gap records named are built (blight, counters read and moved by kind, the
counter-placement ledger, a target floor, divided damage off a life X,
exchanging life with toughness, `activated_by`, damage that can't be
prevented, wither for every source, and a sacrificed source's counters). What
is left is Riveteers Overlook, which the DSL already expresses: its gap record
names gate 4 of `cards.authoring.verify`, which allows a permanent to end only
on the battlefield (an Aura also in the graveyard), while the card's own enters
trigger sacrifices it. `tests/cards/test_authoring.py` pins that a creature
whose text is "When this creature enters, sacrifice it." must still fail that
gate, so admitting the land is the owner's decision, below.

## The change

Blight Curse ships native, card for card, as one batch of
[every precon native](#every-precon-native-one-at-a-time-then-every-import), which holds the procedure:

1. `/author-cards` by name over the `--missing` list.
2. One `/extend-dsl` run per capability the gap records name, in the order
   the most cards elsewhere in the catalog wait on it.
3. Re-author until `--missing` is empty, then `--write-deck ecc_blight_curse`, the
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

- **A permanent whose own text sacrifices it on entering.** Riveteers Overlook
  ("When this land enters, sacrifice it. When you do, search your library for
  a basic Swamp, Mountain, or Forest card, put it onto the battlefield tapped,
  then shuffle and you gain 1 life.") ends in the graveyard as printed, and
  gate 4 rejects it. May gate 4 admit the graveyard for a permanent whose
  unconditional enters trigger opens by sacrificing itself and goes on to a
  reflexive "when you do" ability, the way it admits an Aura? Recommended:
  yes, narrowed to that shape (a `self_enters` trigger with no condition whose
  first effect sacrifices `self_only` and whose next is a `reflexive_trigger`),
  so the pinned vanishing creature, which has no reflexive half, still fails
  and nothing else the gate catches moves; the expectation then has to assert
  what the reflexive half did (the fetched land and the life), which a card
  that merely vanished cannot.
