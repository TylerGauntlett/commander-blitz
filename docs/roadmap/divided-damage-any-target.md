---
id: divided-damage-any-target
title: Divided damage that may hit players
area: cards
effort: M
impact: medium
why: every 'divided as you choose among any number of targets' burn spell waits on it, Magma Opus and Arc Lightning among them
depends_on: []
status: proposed
---

## Today

Divided damage (601.2d) is announced as the spell is cast and dealt on
resolution, but only among permanents. `cards.loader` refuses a `damage`
effect with `divided` whose target spec is not `kind: "permanent"`;
`Game._ask_damage_division` keeps only the declared targets whose kind is
`"object"` and walks them through `_divide`, which asks one object at a time
through `ask_objects`; and `effects.ops_life._damage_divided` deals each share
with `damage_permanent`. [rules-coverage.md](../rules-coverage.md#not-implemented)
lists "dividing damage among players or any target" as not implemented.

So every "deals N damage divided as you choose among any number of targets"
spell is unwritable, because a player is a legal target of it. Magma Opus,
in the Prismari Artistry precon, is the card that found it; Arc Lightning and
Fireball's divided mode are the same sentence. Its gap record is
`data/authoring/gaps/magma_opus.json`.

## The change

1. The division carries players. `_ask_damage_division` divides over every
   declared target of the spec, object or player, and the shares on the stack
   item's `bindings["distribution"]` name which is which, so a player and a
   permanent with the same number are never confused.
2. The question asked while dividing offers players beside objects. Placing
   one more point is one choice among the declared targets; `ask_objects`
   names objects only, so this is either a target-shaped ask or a decision kind
   of its own (an open question below).
3. `_damage_divided` deals a player's share as damage to that player from the
   source, with everything damage to a player already implies (lifelink,
   infect, commander damage from a commander source, prevention), and a share
   for a player who left the game or became an illegal target is lost (608.2b).
4. The loader accepts `divided` over a spec of `kind: "any"` and
   `kind: "player"`. The verifier's auto-answer table answers the new question,
   or `/author-cards` hangs.
5. Harvest: Magma Opus, then the catalog's other divided-among-any-targets
   cards through the template tier with `--retry` and one `/author-cards` wave.

It does not touch divided combat damage (510.1c) or `distribute_counters`,
whose objects are always permanents.

## Gate

A unit test under `tests/unit/` for divided damage over players and
permanents together: the announcement on casting, each share dealt on
resolution, a player's share lost when that player is no longer a legal
target, lifelink and commander damage counted per share, and the loader
accepting `kind: "any"` while still refusing divided damage on an ability. The
verifier's auto-answer test covers the new question, and Magma Opus's six
gates pass.

## Open questions

- **How the division is asked.** Extend `ask_objects` to accept player
  targets, or add a decision kind for "one more point to which target"?
  Recommended: a target-shaped ask built on the existing target references,
  because the client already renders a player as a target, and a new decision
  kind would need its frontend label and an e2e path for no new rule.
- **Is it an ADR.** Recommended: no; it widens an existing announcement
  (601.2d) without changing what is announced or when, and the line in
  rules-coverage.md moves from "not implemented" to the implemented table.
