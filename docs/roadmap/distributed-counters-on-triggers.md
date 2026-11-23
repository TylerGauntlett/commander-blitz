---
id: distributed-counters-on-triggers
title: Distributing counters from a triggered ability
area: cards
effort: M
impact: medium
why: Broodlord in the Tyranid Swarm precon and every 'when this enters, distribute N counters' creature wait on it
depends_on: []
status: proposed
---

## Today

Distributing counters (601.2d, 602.2b) works only on an activated ability.
`cards.loader`'s `_check_distribution_homes` accepts `distribute_counters` as
a top-level effect of an activated ability and refuses it on a spell, a
trigger and nested in a branch; `Game._activate` asks the division through
`Game._ask_distribution` and stores the shares on the stack item's
`bindings["distribution"]`. `_validate_effect` in `cards/loader/effects.py`
also refuses a computed `amount`. [rules-coverage.md](../rules-coverage.md#not-implemented)
lists "`distribute_counters` on a spell or a triggered ability" as not
implemented. [Distributing counters from a spell](distributed-counters-on-spells.md)
plans the spell half and leaves the trigger half out.

A triggered ability's modes and targets are chosen as it is put on the stack,
in `stack.push_triggered_ability` (603.3d), which is also where its division
has to be announced. Nothing asks it there.

So Broodlord ("When this creature enters, distribute X +1/+1 counters among
any number of other target creatures you control"), the card in the Tyranid
Swarm precon that found it, has no expression; its Ravenous half is already
expressible. Its gap record is `data/authoring/gaps/broodlord.json`
(capability `distribute_counters_trigger`).

## The change

1. `_check_distribution_homes` accepts `distribute_counters` as a top-level
   effect of a triggered ability, keeping the refusal inside branches.
2. `stack.push_triggered_ability` asks the division after the targets, by the
   same `_ask_distribution` walk the activation uses, and stores the shares on
   the stack item's `bindings["distribution"]`; the op's resolution side is
   unchanged, and a target gone by resolution loses its share (608.2b).
3. The `amount` may be a value the trigger can read when it is put on the
   stack, `{"binding": "x"}` for a permanent's cast X among them; each target
   still gets at least one counter, so the targets declared are capped by the
   amount.
4. Harvest Broodlord with `/author-cards`, then one wave over the catalog's
   other "distribute … counters" triggers.

It does not touch the spell half (`distributed-counters-on-spells`) or
divided damage.

## Gate

A unit test under `tests/unit/counters/` for a distributing trigger: the
division is asked as the trigger goes on the stack and not on resolution, every
target gets at least one counter, a target that leaves before resolution
loses its share, and an X of zero declares no targets. Broodlord passes the
six authoring gates in `tests/cards`.
