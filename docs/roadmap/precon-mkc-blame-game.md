---
id: precon-mkc-blame-game
title: Blame Game (Murders at Karlov Manor Commander)
area: decks
effort: L
impact: high
why: a coming-soon tile on the shelf becomes a deck a player can pick
depends_on: [voting, secret-choices]
status: proposed
rank: 51
---

## Today

Blame Game, the Murders at Karlov Manor Commander precon released 2024-02-09, is a
coming-soon shell on the shelf: its row `mkc_blame_game` is in
`data/decks/sources.json` and there is no `data/decks/mkc_blame_game.deck.json`, so
`GET /api/precons/upcoming` serves it.
`python scripts/sync_precons.py --missing mkc_blame_game` lists the cards the engine
lacks, and the gap records in `data/authoring/gaps/` name the capability each
attempted card waits on.

Every card on the list has been through `/author-cards` once. Twenty cards
are left, and each has a gap record naming what it waits on:

- Mob Verdict is a secret council vote, which [voting](voting.md) covers;
  this item depends on it.
- Prisoner's Dilemma and Stalking Leonin choose in secret, which
  [secret choices](secret-choices.md) covers; this item depends on it.
  Stalking Leonin also needs a reveal cost and "activate only once".
- Hot Pursuit and Nelly Borca, Impulsive Accuser need suspect; Hot Pursuit
  also needs a goad that lasts while the enchantment stays and a count of
  players who have lost.
- Immortal Obligation needs a goad and a "can't block creatures you
  control" that last while a duty counter stays.
- Feather, Radiant Arbiter needs a "targets only this" spell trigger and a
  copy for each other creature, as Mirrorwing Dragon does.
- Otherworldly Escort needs a return with new creature types and a
  selector for creatures that dealt damage to you this turn.
- Take the Bait needs a this-turn combat prevention over the planeswalkers
  you control, read as the damage is dealt.
- Comeuppance needs a shield for damage from sources you don't control
  that knows the prevented source.
- Deflecting Palm needs "prevent the next damage a chosen source would
  deal" and its reflection.
- Gisela, Blade of Goldnight needs a static that prevents half of each
  damage event, rounded up.
- Darien, King of Kjeldor needs a trigger for a player being dealt damage,
  once for all damage dealt at the same time.
- Anya, Merciless Angel needs a count of opponents below half their own
  starting life.
- Orzhov Advokist needs an attack restriction lasting until your next turn.
- Soul Snare needs a selector for creatures attacking you or a planeswalker
  you control.
- Smuggler's Share needs one opponent's own count of lands entered this
  turn.
- Curse of Opulence needs the Gold token and a selector for opponents
  attacking the enchanted player.
- Kazuul, Tyrant of the Cliffs needs the 3/3 red Ogre token.
- Rite of the Raging Storm needs the Lightning Rager token and a name filter
  on a static.

## The change

Blame Game ships native, card for card, as one batch of
[every precon native](#every-precon-native-one-at-a-time-then-every-import), which holds the procedure:

1. `/author-cards` by name over the `--missing` list.
2. One `/extend-dsl` run per capability the gap records name, in the order
   the most cards elsewhere in the catalog wait on it.
3. Re-author until `--missing` is empty, then `--write-deck mkc_blame_game`, the
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
