---
id: divided-damage
title: Damage divided among targets on a spell (601.2d)
area: cards
effort: M
impact: medium
why: Monstrous Onslaught in Tramplesaurus Rex and Pyrokinesis wait on it, and every divided-damage spell after them
depends_on: []
status: proposed
---

## Today

A spell cannot divide damage among its targets. The `damage` op in
`engine/effects/ops_life.py` deals its full `amount` to every object its
selector names, so "4 damage divided as you choose among any number of target
creatures" would deal 4 to each. The one dividing op is `distribute_counters`
in `engine/effects/ops_counters.py`, whose division is announced by
`Game._ask_distribution` as an **activated** ability is put on the stack
(601.2d via 602.2b) and carried as `bindings["distribution"]`; `Game._cast`
asks nothing of the kind, and the loader keeps the op to activated abilities
with a printed amount. [rules-coverage.md](../rules-coverage.md) lists
"dividing damage among targets" under "Not implemented".

Two gap records name the capability, `divided_damage`:
`data/authoring/gaps/monstrous_onslaught.json`, the last card the Tramplesaurus
Rex precon lacks, and `data/authoring/gaps/pyrokinesis.json`. Monstrous
Onslaught also needs its X, "the greatest power among creatures you control
**as you cast this spell**", fixed at cast time: `extreme_value` reads the
board only as the spell resolves.

## The change

1. A `divided` key on the `damage` op (or a sibling op), naming one target spec
   whose objects share the `amount`. `Game._cast` announces the division after
   the targets and before payment (601.2d), through the same one-at-a-time
   `ask_objects` walk `_ask_distribution` uses, every target taking at least one,
   and records it on the stack item; resolution deals each still-legal target its
   share and redistributes nothing (608.2b).
2. A value fixed as the spell is cast, for an amount that 601.2d needs to know
   before the division: the amount is evaluated at announcement and carried on
   the stack item rather than re-read on resolution.
3. The verifier's auto-answer handles the division without a new decision kind,
   since it composes `ask_objects`.
4. Harvest Monstrous Onslaught and Pyrokinesis through `/author-cards`, then
   finish [precon-fdc-tramplesaurus-rex](precon-fdc-tramplesaurus-rex.md),
   which depends on this item.

It does not touch combat damage assignment (510.1c), which stays as it is.

## Gate

A unit test under `tests/unit/damage/` that casts a divided-damage spell at two
and three targets and asserts each target's damage, that every target was
assigned at least one, that a target made illegal in response loses its share
without the rest moving, and that the cast-time amount does not change when the
board does before resolution; `tests/cards` with Monstrous Onslaught and
Pyrokinesis through the six gates.

## Decisions

- **One op or a key:** a `divided` key on the `damage` op, naming the target
  spec whose objects share the `amount`. The effect is damage in every other
  respect (lifelink, deathtouch, `damage_multiplier`, prevention), and a sibling
  op would have to re-route all of it.
- **How the cast-time amount is written:** a field on the divided damage that
  says its amount is evaluated at announcement, not a general `as_cast` wrapper.
  601.2d only needs the amount fixed where a division is announced, and a
  general wrapper would open every value to cast-time reads no other card needs
  yet.
- **Scope of the pull request:** one pull request titled `feat(cards):` with the
  capability, Monstrous Onslaught and Pyrokinesis, and the Tramplesaurus Rex
  deck written once Monstrous Onslaught lands, so
  [precon-fdc-tramplesaurus-rex](precon-fdc-tramplesaurus-rex.md) retires in the
  same pull request. Combat damage assignment (510.1c) is not touched.
