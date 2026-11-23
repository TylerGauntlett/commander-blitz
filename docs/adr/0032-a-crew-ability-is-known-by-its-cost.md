# ADR 0032 — A crew ability is known by its cost

**Status:** accepted

## Context

Rule 702.122d says a Vehicle "becomes crewed" when a crew ability of it
resolves, and "whenever this Vehicle becomes crewed" (Mobilizer Mech, Ghost Ark)
triggers then. The engine therefore has to tell a crew ability from every other
activated ability as the ability resolves, whatever put it on the stack: a copy
of the crew ability crews the Vehicle too, and an ability that only animates a
Vehicle ("another target Vehicle becomes an artifact creature") does not.

The card format has no crew keyword. Crew is written out as what 702.122a says
it is: an activated ability with a `tap_permanents` cost carrying `total_power`,
whose effect animates the Vehicle. Equip and boast are recognised by explicit
markers (`is_equip`, `is_boast`) because their costs are ordinary; nothing in an
equip cost says "equip". Crew's cost is not ordinary: `total_power` is a sum of
power, and no other printed tap cost is one.

## Decision

A crew ability is an activated ability whose cost carries `total_power` on
`tap_permanents`. `Ability.is_crew` reads that, and `stack._resolve_ability`
fires `became_crewed` for the ability's source after its effects, when the
source is still on the battlefield.

The loader holds the converse, so the marker cannot be borrowed:
`_check_crew_shape` refuses a `total_power` tap cost on any ability that is not
activated, or whose effects are anything but one `animate` of `objects`
`self_only`.

## Consequences

**Good.** Every crew ability written before the event existed fires it, with no
card rewritten and no new key for an author to forget. A copied crew ability
crews, because the copy has the same cost-bearing ability. An animation from any
other source never crews.

**Bad.** A future printed cost that sums power without being crew ("tap any
number of creatures with total power 10: draw a card") cannot use `total_power`
as it stands; it needs its own key, or this decision revisited with an explicit
`is_crew` marker. A crew line with a rider must be written as a separate
`becomes_crewed` trigger, which is also what the printed card means.

**Cost of reversing.** Moderate. Moving to an explicit marker means adding it to
every crew ability in `data/cards/`, through the crew template and a
re-collection, or Vehicles stop becoming crewed.
`tests/unit/triggers/test_becomes_crewed.py` pins the recognition and the
loader's refusals.
