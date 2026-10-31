---
id: distributed-counters-on-spells
title: Distributing counters from a spell
area: cards
effort: M
impact: medium
why: every 'distribute N counters among any number of target creatures' spell waits on it, Grove's Bounty in the Quandrix Unlimited precon and Biogenic Upgrade among them
depends_on: []
status: proposed
---

## Today

Distributing counters (601.2d, 602.2b) works only on an activated ability.
`cards.loader`'s `_check_distribution_homes` accepts `distribute_counters` as
a top-level effect of an activated ability and refuses it in `spell_effects`,
on a trigger and nested in a branch; `Game._activate` asks the division
through `Game._ask_distribution`, which walks the declared targets with
`_divide` and stores the shares on the stack item's
`bindings["distribution"]`. `_validate_effect` in `cards/loader/effects.py`
also refuses a computed `amount`, so "distribute X counters" is refused even
where the op is allowed. [rules-coverage.md](../rules-coverage.md#not-implemented)
lists "`distribute_counters` on a spell or a triggered ability" as not
implemented.

The spell half of the same announcement already exists for damage:
`Game._ask_damage_division` divides a spell's `divided` damage on the cast
line, after targets and X are chosen, under the purpose tag `divide_damage`.

So every "distribute N +1/+1 counters among any number of target creatures"
instant or sorcery is unwritable. Grove's Bounty, the Adventure half of
Elusive Otter in the Quandrix Unlimited precon, is the card that found it
(with X as the number); Biogenic Upgrade, Abzan Charm's third mode, Bounty of
the Hunt and Elven Rite are the same sentence. Its gap record is
`data/authoring/gaps/elusive_otter_grove_s_bounty.json`, which also names a
second, unrelated need (a block restriction by relative power).

## The change

1. `_check_distribution_homes` accepts `distribute_counters` as a top-level
   effect of `spell_effects`, keeping the refusal on triggers and inside
   branches.
2. `Game._cast` asks the division on the cast line the way it asks divided
   damage, after modes, X and targets (601.2d), by calling
   `_ask_distribution` over the spell's effects and storing the shares on the
   stack item's `bindings["distribution"]`; the op's resolution side is
   unchanged.
3. The `amount` may be `{"x": true}` on a spell, read from the X announced
   before the division; each target still gets at least one counter, so a
   target ceiling larger than the amount stays refused for a printed number,
   and for X the cast line is withheld when X is smaller than the number of
   targets declared.
4. Harvest: Elusive Otter once its other need is built, then the catalog's
   other distribute-from-a-spell cards through the template tier with
   `--retry` and one `/author-cards` wave.

It does not add distribution on a triggered ability (603.3d), which announces
the division as the trigger is put on the stack, nor touch divided damage
(`divided-damage-any-target`).

## Gate

A unit test under `tests/unit/` for `distribute_counters` on a spell: the
division asked on casting with the announced X, the shares bound on the stack
item, each share placed on resolution, a share lost when its target is no
longer legal (608.2b), a cast with fewer counters than targets refused, and
the loader still refusing the op on a trigger. Biogenic Upgrade's six gates
pass.

## Open questions

- **Scope of X.** Accept a computed `amount` only as `{"x": true}`, or any
  value expression? Recommended: only X, because 601.2d needs the total known
  when the division is announced, and X is the one computed number fixed by
  then.
- **Triggers in the same pull request.** Recommended: no; a trigger announces
  its division at 603.3d, in `stack` rather than `Game._cast`, and no card in
  a precon on the roadmap needs it yet.
- **Is it an ADR.** Recommended: no; it moves an existing announcement to the
  cast line, where divided damage already sits, and the line in
  rules-coverage.md narrows to triggered abilities.
