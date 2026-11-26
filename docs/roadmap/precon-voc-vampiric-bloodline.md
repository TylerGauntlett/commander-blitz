---
id: precon-voc-vampiric-bloodline
title: Vampiric Bloodline (Crimson Vow Commander)
area: decks
effort: M
impact: high
why: a coming-soon tile on the shelf becomes a deck a player can pick
depends_on: [exact-target-count]
status: proposed
rank: 94
---

## Today

Vampiric Bloodline, the Crimson Vow Commander precon released 2021-11-19, is a
coming-soon shell on the shelf: its row `voc_vampiric_bloodline` is in
`data/decks/sources.json` and there is no `data/decks/voc_vampiric_bloodline.deck.json`, so
`GET /api/precons/upcoming` serves it.
`python scripts/sync_precons.py --missing voc_vampiric_bloodline` lists the cards the engine
lacks, and the gap records in `data/authoring/gaps/` name the capability each
waits on. They fall into three groups:

- **Madness.** `replacements._madness` leaves a madness card its owner declines
  to cast in exile, and `docs/rules-coverage.md` and the cookbook's "madness
  exiles either way" row record that as the engine's reading. 702.35a and the
  printed reminder text put it into the graveyard instead. Anje's Ravager,
  Stensia Masquerade and Stromkirk Occultist wait on that alone. Avacyn's
  Judgment also needs an `{X}` madness cost and an "if this spell's madness
  cost was paid" condition; Shadowgrange Archfiend a madness cost with
  `pay_life` in it and the greatest last-known power among sacrificed
  creatures; Falkenrath Gorger a static that grants madness.
- **Exact target counts.** Sinister Waltz's "three target creature cards"
  needs `targeting._spec_options` to refuse a short set
  ([exact-target-count](#a-fixed-target-count-is-exact-not-a-ceiling)), and
  then the authoring sandbox (`cards/authoring/verify.py`,
  `graveyard_target_props`) to put a third creature card in its own graveyard
  so the playable gate can cast it.
- Nothing else: every other card on the list is native.

## The change

Vampiric Bloodline ships native, card for card, as one batch of
[every precon native](#every-precon-native-one-at-a-time-then-every-import), which holds the procedure:

1. `/author-cards` by name over the `--missing` list.
2. One `/extend-dsl` run per capability the gap records name, in the order
   the most cards elsewhere in the catalog wait on it.
3. Re-author until `--missing` is empty, then `--write-deck voc_vampiric_bloodline`, the
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

- **A declined madness card.** The engine's madness exiles the card whether or
  not it is cast, and that reading is written into `rules-coverage.md`, the
  cookbook and `tests/unit/replacement/test_draw_and_discard_replacements.py`,
  so changing it reverses a recorded rules decision, which the run will not do
  unattended. Should a declined (or uncastable) madness card go to its owner's
  graveyard? Recommended: yes, as 702.35a and every printed reminder text say
  ("cast it for its madness cost or put it into your graveyard"); the move is
  one line in `replacements._madness` after `_offer_cast` returns false, the
  tests that pin the exile are rewritten to pin the graveyard, and the two doc
  rows are rewritten to match. Then the other madness needs above are one
  `/extend-dsl` run each.
