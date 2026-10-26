# ADR 0027 — Rule-modifying statics read derived characteristics

**Status:** accepted

## Context

[ADR 0001](0001-layers-lite.md) applies continuous effects in a fixed order and
forbids a static ability's filter from reading another static's output, so the
static filter language matches printed characteristics plus board state. That
rule exists to keep the layer pipeline acyclic: a layered static whose filter
read a layered static's result would need 613.8 dependency ordering.

Some statics the filter language describes are not layered at all. An attack
requirement (`attacks_if_able`, 508.1d) and a block restriction
(`block_restriction`, 509.1b) change the rules of combat, not any object's
characteristics, so the pipeline never applies them and their answer cannot feed
back into a layer. Reading printed characteristics there is simply wrong: Graaz,
Unstoppable Juggernaut makes every other creature you control a Juggernaut with
an `add_subtype` static, and its "Juggernauts you control attack each combat if
able" and "can't be blocked by Walls" must reach those creatures.

## Decision

`characteristics._matches` takes `derived`. With it, the filter reads the
object's characteristics off `chars()` (types, subtypes, supertypes, keywords,
colours, power and toughness after every layer). `player_statics.attack_compelled`
and `characteristics.block_restrictions` match `affects` with it, and
`combat.can_block` matches a restriction's `blockers` with it. Every reader
inside the pipeline keeps the printed match.

## Consequences

**Good.** The rule-modifying statics see the board the players see, so a type,
colour, keyword or size granted by any static counts. No recursion is possible:
`chars()` never asks an attack requirement or a block restriction anything.

**Bad.** The filter language now has two readings, chosen by the reader and not
by the card; a filter key behaves differently in a `buff` and in an
`attacks_if_able`. The loader still validates both against the same key list.

**Cost of reversing.** Small, and wrong: dropping `derived` from one of the three
call sites makes Graaz bind only itself. `tests/unit/combat/test_derived_rule_filters.py`
pins all three.

## Alternatives considered

**Rewrite the card's filter as "creatures you control".** Diverges from the
printed card under a text change on Graaz or a later type-removing effect.

**A real layer system with dependencies.** Not needed: no layered static is
involved in the dependency.
