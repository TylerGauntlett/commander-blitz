---
id: divided-damage-on-abilities
title: Divided damage from a triggered or activated ability
area: cards
effort: M
impact: medium
why: every creature whose enters or attack trigger divides its damage waits on it, Fury and Inferno Titan among them
depends_on: []
status: proposed
---

## Today

Divided damage (601.2d) is announced on one line only: as a spell is cast.
`Game._ask_damage_division` reads `engine.division.divided_damage(card)`,
which walks `card.spell_effects`, and is called from `Game._cast`; the split
rides on the stack item's `bindings["distribution"]` and
`effects.ops_life._damage_divided` deals it on resolution.
`cards.loader._check_division_homes` refuses `damage` with `divided` anywhere
else ("only supported as a top-level effect of a spell"), and
[rules-coverage.md](../rules-coverage.md#not-implemented) lists dividing
damage "on an ability" as not implemented.

The ability-level twin already exists for counters: `distribute_counters` on
an activated ability is divided by `Game._ask_distribution` at activation
(602.2b applying 601.2d), composed from `ask_objects` with no decision kind of
its own. A triggered ability chooses its modes and targets in
`stack._choose_trigger_targets` as it is put on the stack (603.3d), and
nothing there asks for a division.

So "When this creature enters, it deals 4 damage divided as you choose among
any number of target creatures and/or planeswalkers" is unwritable. Fury, in
the Dance of the Elements precon, is the card that found it; its gap record is
`data/authoring/gaps/fury.json`.

## The change

1. The trigger line divides. Where `stack` puts a triggered ability on the
   stack and has chosen its targets, a `damage` effect with `divided` among
   the ability's top-level effects is divided over the targets just declared,
   through the same walk `_ask_damage_division` uses, and stored on the stack
   item's `bindings["distribution"]` so `_damage_divided` resolves it
   unchanged. The amount is read then (601.2d via 603.3d).
2. The activation line divides damage the way it already divides counters:
   `Game._ask_distribution` takes divided `damage` beside
   `distribute_counters`.
3. `_check_division_homes` accepts divided damage as a top-level effect of a
   triggered or activated ability whose spec targets objects, and still
   refuses it nested in a branch, where no announcement exists.
4. The verifier's auto-answer table answers the division on the trigger line,
   or `/author-cards` hangs on Fury.
5. Harvest: Fury (which also waits on evoke with a non-mana cost) and the
   catalog's other divided-damage triggers through the template tier with
   `--retry` and one `/author-cards` wave.

It does not let the division include players: that is
[divided-damage-any-target](divided-damage-any-target.md), which this item
neither needs nor blocks. Inferno Titan needs both.

## Gate

A unit test under `tests/unit/` for divided damage on a trigger and on an
activation: the division asked as the trigger goes on the stack and before a
response is possible, each share dealt on resolution, an illegal target's share
lost (608.2b), the forced split asking nothing, and the loader accepting the
top-level ability home while still refusing a nested one. The verifier's
auto-answer test covers the trigger-line question, and the harvested cards pass
their six gates.

## Open questions

- **Where the trigger's division is asked.** In `stack` beside
  `_choose_trigger_targets`, or by handing the trigger to the same
  `Game` helper the cast and activation lines use? Recommended: one shared
  helper called from all three lines, because the walk and its purpose tag are
  already shared and a third copy would drift.
- **Is it an ADR.** Recommended: no; it applies the existing announcement
  (601.2d) on the two lines 602.2b and 603.3d already send it to, and the
  rules-coverage.md line moves to the implemented table.
- **Scope of the harvest.** Fury only, or every divided-damage trigger the
  template tier can then read? Recommended: one template-tier `--retry` and
  one `/author-cards` wave, the precon items' convention.
