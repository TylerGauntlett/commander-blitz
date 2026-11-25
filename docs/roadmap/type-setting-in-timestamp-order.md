---
id: type-setting-in-timestamp-order
title: A type-setting static ordered against later animations
area: cards
effort: M
impact: medium
why: Swift Reconfiguration's crewed permanent never becomes a creature, and it alone keeps Buckle Up off the shelf
depends_on: []
status: proposed
adr: true
---

## Today

Swift Reconfiguration prints "Enchanted permanent is a Vehicle artifact with
crew 5 and it loses all other card types. (It's not a creature unless it's
crewed.)". The DSL has every word of it: a `set_types` static to
`["Artifact"]`, an `add_subtype` static for Vehicle and a `grant_ability`
static handing over a crew whose `animate` adds Creature. What it lacks is
the order. `characteristics._compute` applies every animation, timed and
indefinite, in timestamp order first (step -1), and only then every
`set_types` static (step 0), which replaces the type set outright. So a
crew animation that began after the Aura arrived is always erased: the
enchanted permanent can be crewed and never becomes a creature, a silently
wrong card. Under 613.7 the later animation applies over the earlier static.

That order is [ADR 0001](../adr/0001-layers-lite.md)'s: continuous effects
in a fixed order rather than by timestamp. The engine already bends it
inside layer 4 where a rule names a timestamp: the animations sort among
themselves, and impending and a Duplicant's imprint sit ahead of them as the
permanent's own arrival. A `set_types` static has a timestamp too, its
source's (`static_timestamp`), and nothing reads it there. The gap record
is `data/authoring/gaps/swift_reconfiguration.json`, under
`type_setting_in_timestamp_order`. `tests/unit/statics/test_conditional_types.py`
and `tests/unit/copies/test_enters_as_copy_set_types.py` hold what
`set_types` does today.

## The change

1. An amendment to ADR 0001 recording that `set_types` statics apply in
   layer 4 in timestamp order with the animations, each against the others,
   and why a fixed order was wrong for this one pair.
2. `characteristics._compute` reads the `set_types` statics into the same
   sorted pass as the animations, keyed on `static_timestamp` of their
   source, so whichever began later wins. Nothing else in the fixed order
   moves: the creature-type replacement, the subtype grants and every layer
   after 4 stay where they are.
3. Harvest: Swift Reconfiguration through `/author-cards`, its gap record
   retired, and the precon item that waits on it unblocked.

It does not order any other static by timestamp, and it does not add
dependency analysis.

## Gate

A unit test under `tests/unit/statics/` that an Aura setting a creature's
types to Artifact, crewed afterwards, is an artifact creature until end of
turn and an artifact again after cleanup; that an animation older than the
`set_types` static is still overwritten by it (Imprisoned in the Moon on an
already-animated land); and the existing `set_types` tests unchanged and
green. Swift Reconfiguration's six gates.

## Open questions

- **May `set_types` statics join the timestamp-ordered pass, amending ADR
  0001?** Recommended: yes, for `set_types` alone. The animations already
  sort by timestamp in the same layer, so this extends an existing exception
  rather than starting the layer system, and the alternative, leaving the
  card unauthored, keeps Buckle Up off the shelf for one card.
- **Is a crew animation a timed animation for this ordering, whatever the
  Aura's timestamp?** Recommended: yes. The crew effect always begins after
  the Aura that granted the crew, so the plain timestamp comparison gives
  the printed reminder text, "It's not a creature unless it's crewed".
