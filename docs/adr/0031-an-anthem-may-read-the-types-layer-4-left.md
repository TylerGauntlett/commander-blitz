# ADR 0031 — An anthem's filter may read the types layer 4 left

**Status:** accepted

## Context

[ADR 0001](0001-layers-lite.md) applies continuous effects in a fixed order and
forbids a static ability's filter from reading another static's output, so a
layered static's `affects` matches printed characteristics plus board state.
[ADR 0027](0027-rule-modifying-statics-read-derived-characteristics.md) let the
statics no layer applies read derived characteristics, and kept the printed
match for every reader inside the pipeline. The recorded consequence is that a
type granted by a static is in `chars()` and invisible to another static's
filter.

The Flesh Is Weak prints "Creatures you control with +1/+1 counters on them are
artifacts in addition to their other types. Nonartifact creatures get -1/-1."
The first sentence is a layer-4 type change (613.1d); the second is a layer-7c
P/T change (613.4c) whose set of affected objects is decided when layer 7c is
applied, after layer 4 has been applied in full (613.1). Matched on printed
types, the -1/-1 reaches the creatures the first sentence made artifacts, which
inverts the card.

That read is ordered, not a dependency. Rule 613.8 orders effects only within
one layer or sublayer (613.8a). A layer-7c effect reading layer 4's result is
the layer system working as written, and no layer-4 effect can read a layer-7c
result back, so no loop is possible. In `_compute` the object's types are final
when the anthem step runs: the step can read the working sets that the
type-changing steps above it produced, and does not have to call `chars()`.

## Decision

A `buff` static's `affects` may carry `derived_types: true`. Its type clauses
(`types`, `any_types`, `not_types`, `subtypes`, `not_subtypes`, `supertypes`,
`not_supertypes`) then read the object's card types, subtypes and supertypes as
the layer-4 steps of `characteristics._compute` left them. Every other clause
keeps its reading. `_compute` passes those sets to `_matches` at the anthem
step, and `_matches` raises `DslError` if it is asked the key without them.

The loader admits the key on `buff` only, as `true`, on the outer filter and
not inside an `any_of` branch, and only beside a type clause it changes.

## Consequences

**Good.** The Flesh Is Weak is the printed card. The read stays acyclic by
construction: the type sets come from the object's own computation, and no
reader before layer 7c is offered the key.

**Bad.** The reading is chosen by the card, not by the rules. An anthem without
the key still reads printed types, so a Xenograft naming Goblin does not put
Bears under a Goblin lord, and an author must add the key where a type grant
matters. Layer 6 (`grant_keyword`) and layer 7b (`set_pt`) are equally later
than layer 4 but do not take the key: `grant_keyword` statics also have readers
outside `_compute` (`keyword_as_it_enters`, `annihilator_instances`), which do
not hold the working sets.

**Cost of reversing.** Small. Dropping the key makes The Flesh Is Weak shrink
the creatures it made artifacts. `tests/unit/statics/test_derived_types_filter.py`
pins the read, the boundary and the load-time refusals.

## Alternatives considered

**Make every anthem read layer-4 types.** The rules-exact default, but it
changes the reading of every authored anthem in one change, card by card
unreviewed, and reverses the Xenograft consequence for cards that never asked.

**A dependency system (613.8).** Not needed: the read crosses layers, and 613.8
is about effects within one layer.

**Rewrite the sentence as "creatures without +1/+1 counters".** Diverges as soon
as anything else makes a creature an artifact or removes the type.
