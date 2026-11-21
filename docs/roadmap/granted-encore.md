---
id: granted-encore
title: Encore, granted to cards in a graveyard
area: cards
effort: M
impact: medium
why: every card that hands encore to the creature cards in your graveyard waits on it, Wire Surgeons in the Urza's Iron Alliance precon among them
depends_on: []
status: proposed
---

## Today

Encore (702.141) is not a keyword the engine knows: `engine/enums.py` lists no
`encore`, and no card key or op spells "exile this card from your graveyard:
for each opponent, create a token copy that attacks that opponent this turn
if able; they gain haste; sacrifice them at the beginning of the next end
step; activate only as a sorcery". Its pieces exist apart: a graveyard
activated ability is a printed ability whose `active_zones` names the
graveyard (embalm, read by `legality._activate_zones`), `copy_permanent`
makes the token copies (its `embalm` key stamps the provenance), and delayed
sacrifice is the `delay` op.

The cards that wait on it grant encore rather than print it. A grant cannot
reach the graveyard: `characteristics.abilities_of` derives granted abilities
on a permanent only and off the battlefield returns the printed list, and the
loader refuses a granted activated ability whose `active_zones` is anything
but the battlefield ("a granted activated ability works on the battlefield
only", `cards/loader/__init__.py`).
[rules-coverage.md](../rules-coverage.md#not-implemented) lists "a granted
activated ability that works off the battlefield (granted cycling)" as not
implemented, and [granted-cycling](granted-cycling.md) is the same gap from
the hand.

The grants price encore by the card it lands on, which nothing can say today:
Wire Surgeons ("each artifact creature card in your graveyard has encore. Its
encore cost is equal to its mana cost") and Graywater's Fixer ("each outlaw
creature card in your graveyard has encore {X}, where X is its mana value").
Their gap records are `data/authoring/gaps/wire_surgeons.json` and
`data/authoring/gaps/graywater_s_fixer.json`, under the capability `encore`.

## The change

1. Encore as a card's own keyword: a graveyard-zone activated ability at
   sorcery speed whose cost is the encore mana plus exiling the card, and whose
   effect makes one `copy_permanent` token per opponent with haste, required
   to attack that opponent this turn (508.1d), and a delayed sacrifice at the
   beginning of the next end step.
2. A `grant_encore` player-wide static in `grant_miracle`'s shape: an
   `affects` filter over the cards in its controller's graveyard and an
   `encore_cost` of either a mana string, `"mana_cost"` (the card's own) or
   `"mana_value"` (generic equal to it).
3. `characteristics.abilities_of` appends, for a graveyard card a
   `grant_encore` static matches, the encore ability built the way a printed
   one is, after the printed abilities so printed indices never move; the
   stack push records the grant, as `stack.push_activated_ability` records
   `granted_by` for a battlefield grant (608.2).
4. The rules-coverage row for graveyard grants moves out of "Not
   implemented"; the generator's curated map and `docs/card-dsl.md` gain the
   keyword and the static.
5. Harvest: Wire Surgeons and Graywater's Fixer, then one `/author-cards` wave
   over the pending cards that print encore.

It does not grant cycling to the hand; that is [granted-cycling](granted-cycling.md),
which this item's `abilities_of` seam would share if it lands first.

## Gate

A unit test under `tests/unit/keywords/` for encore: in a three-player game the
ability makes one hasty token per opponent, each must attack its own opponent,
each is sacrificed at the next end step, the card is exiled as the cost, and it
is offered only at sorcery speed. A unit test for the grant: a matching card in
the graveyard offers encore at each pricing, a non-matching one does not, and
the offer disappears when the granting permanent leaves. Wire Surgeons' and
Graywater's Fixer's six gates pass, and `tests/cards/test_dsl_reference.py`
lists the new keyword and static.

## Open questions

- **One item or two.** Printed encore and the graveyard grant are separable:
  printed encore needs no new zone grant. Recommended: one pull request, since
  no precon card prints encore without a grant waiting on it, and the grant's
  test needs the keyword.
- **A player static or a widened `grant_ability`.** Recommended: a dedicated
  `grant_encore` player static, for the reasons [granted-cycling](granted-cycling.md)
  gives: every precedent for handing something to cards in a hidden or
  off-battlefield zone is a player static, and the battlefield grant's loader
  check stays intact.
- **"Attacks that opponent this turn if able".** The engine's requirement to
  attack is a creature's, not a creature-and-player pair's. Recommended: a
  per-token attack requirement naming the defending player, checked where
  `combat` validates declared attackers, rather than a goad, which would also
  forbid attacking its controller's other opponents and lasts the wrong time.
