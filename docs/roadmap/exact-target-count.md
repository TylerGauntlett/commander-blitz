---
id: exact-target-count
title: A fixed target count is exact, not a ceiling
area: play
effort: M
impact: medium
why: every "N target" spell can be cast today with fewer targets than it prints, which makes it a cheaper card than the paper one
depends_on: []
status: proposed
---

## Today

A target spec with a literal `count` and no `up_to` is printed as an exact
number ("six target permanents"), and 601.2c asks for exactly that many.
`targeting._spec_options` enumerates the choices as combinations of
`min(count, len(options))` candidates, so with fewer legal candidates than the
count the spell is offered with a short set: Aether Gale can be cast with one
permanent on the table. The one exception is `one_per_player` on an exact count,
which asks for the full size (Run Away Together). Making every fixed count exact
breaks `tests/unit/keywords/test_monstrosity.py`, whose position relies on the
short set.

## The change

1. `_spec_options` asks for the full `count` on every fixed-size spec without
   `up_to`, as it already does under `one_per_player`; a spell with too few
   candidates has no cast line, and a triggered ability with too few is
   removed from the stack (603.3d).
2. The Monstrosity test's position is given enough candidates, or reads the
   card the way it is printed, whichever the card says.
3. `tests/cards` is the witness that no shipped card relied on the short set;
   any card it fails was authored against the bug and is re-collected, never
   hand-edited.

It does not change `up_to`, `min_count` or "any number" specs.

## Gate

A unit test under `tests/unit/targets/` that a "two target creatures" spell has
no cast line with one creature on the battlefield and one with two, and that a
triggered ability with too few candidates leaves the stack; `tests/cards`
green.

## Open questions

- **Triggered abilities.** Should a trigger with too few candidates be removed
  (603.3d) or fire with what there is? Recommended: removed, as the rules say,
  in the same pull request, since the enumeration is shared.
- **Cards that break.** If `tests/cards` shows shipped cards that only pass
  with a short set, are they re-collected here or each filed as a gap?
  Recommended: re-collected here, since the fix is what makes them right.
