---
id: granted-cycling
title: Cycling granted to cards in hand
area: cards
effort: M
impact: medium
why: every card that hands cycling to the cards in your hand waits on it, Rhet-Tomb Mystic in the Eternal Might precon among them
depends_on: []
status: proposed
---

## Today

Cycling (702.29) is a card's own activated ability with `active_zones` naming
the hand, a cost that discards the card and the `cycle` event fired before the
draw; `legality._activate_zones` walks the player's hand for it and
`legality._ability_aims` gates each ability on `Ability.active_zones`.

A grant cannot reach it. `characteristics.abilities_of` derives granted
abilities on a permanent only, and off the battlefield returns the printed
list; the loader refuses a granted activated ability whose `active_zones` is
anything but the battlefield (the `grantable` check in
`cards/loader/__init__.py`, "a granted activated ability works on the
battlefield only"). [rules-coverage.md](../rules-coverage.md#not-implemented)
lists "a granted activated ability that works off the battlefield (granted
cycling)" as not implemented.

The nearest precedents are player-wide statics that hand a cost to cards in
hand: `grant_miracle` (`player_statics.granted_miracle_cost`, read by
`replacements._miracle`) and `grant_warp` (`granted_warp_cost`), each matching
the card with `_matches_printed` against an `affects_spells` filter.

So Rhet-Tomb Mystic ("Each creature card in your hand has cycling {1}{U}"),
the Eternal Might precon's card that found it, cannot be written; its gap
record is `data/authoring/gaps/rhet_tomb_mystic.json`, under the capability
`grant_cycling_to_cards_in_hand`.

## The change

1. A `grant_cycling` player-wide static in `grant_miracle`'s shape: an
   `affects_spells` filter over the cards in its controller's hand and a
   `cycling_cost`, read through `_active_player_statics` so its `condition`
   is honoured.
2. `characteristics.abilities_of` appends, for a card in hand that a
   `grant_cycling` static matches, one cycling ability built the way a
   printed one is (hand-only `active_zones`, the mana plus discarding the
   card, `is_cycling`, draw a card), after the printed abilities so printed
   indices never move. Legality, payment and `game._activate` already read
   `abilities_of`, so the hand offers it and the `cycle` event fires.
3. A cycled card that was granted the ability resolves its draw after it has
   left the hand: the push records the grant the way
   `stack.push_activated_ability` records `granted_by` for a granted
   battlefield ability (608.2).
4. The rules-coverage row moves out of "Not implemented"; the generator's
   curated map and `docs/card-dsl.md` gain the static.
5. Harvest: Rhet-Tomb Mystic, then one `/author-cards` wave over the pending
   cards the static reaches.

It grants cycling only. A granted typecycling, landcycling or a granted
ability from the graveyard (embalm) is not part of it, and a cycling cost
reduction is not either.

## Gate

A unit test under `tests/unit/` for granted cycling: a matching card in hand
offers a cycling action that a non-matching card does not, paying it discards
the card and draws, a `cycle` trigger fires off it, the action disappears when
the granting permanent leaves, and a card with printed cycling keeps its own
ability at its own index. Rhet-Tomb Mystic's six gates pass, and the generated
DSL reference (`tests/cards/test_dsl_reference.py`) lists the new static.

## Open questions

- **A player static or a widened `grant_ability`.** `grant_ability` already
  hands abilities to permanents through `abilities_of`; widening its
  `affects` to a hand zone reuses the grantable-ability plumbing but puts a
  hidden-zone walk into every battlefield grant. Recommended: a dedicated
  `grant_cycling` player static in `grant_miracle`'s shape, since every
  precedent for handing something to cards in hand is one, and it keeps the
  battlefield grant's loader check intact.
- **Where the ability is derived.** In `abilities_of` for a card in hand, or
  in `legality` as an extra action. Recommended: `abilities_of`, because
  legality, the payment solver and resolution all read it, so the three cannot
  disagree about the ability's index.
- **Two grants.** Two Rhet-Tomb Mystics, or a printed cycling plus a grant,
  are two cycling abilities by the rules (702.29). Recommended: the first
  grant wins over another grant, as `granted_miracle_cost` does, while a
  printed cycling and a grant stay two offers, since their costs differ.
