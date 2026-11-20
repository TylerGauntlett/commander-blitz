---
id: flashback-permission-cap
title: Granted flashback permissions without a per-turn cap
area: cards
effort: S
impact: medium
why: Lier, Return the Past and The Great Work each let one instant or sorcery out of the graveyard a turn, where the printed card lets every one go
depends_on: []
status: proposed
---

## Today

A permission to cast from a graveyard is metered by `max_per_turn`, read in
`casting._permission_reaches`: an explicit `None` is uncapped, a missing key is
one cast a turn, unless the permission grants escape or retrace. The count is
billed per granting object through `TurnLedger` under `GRAVEYARD_CAST_SLOT`.

Flashback's exile is the brake for a permission that grants it (702.34a, the
`StackItem.exiles_instead` stamp in `Game._cast`). The two loaders say so:
the `cast_from_graveyard` refusal in `cards/loader/__init__.py` ("Lier prints
no per-turn cap and needs none") and the `grant_graveyard_cast` guard in
`cards/loader/effects.py::_validate_effect`. Neither compiles that way:

- The static's compile in `cards/loader/__init__.py` writes `max_per_turn: 1`
  for a `grants_flashback` static with no printed cap; only `escape`,
  `grants_retrace` and a non-flashback `surveilled_this_turn` get `None`.
  Lier, Disciple of the Drowned and Return the Past are capped at one cast a
  turn.
- `effects/ops_cards.py::op_grant_graveyard_cast` copies the spec into the
  static as written, and a `grants_flashback` grant carries no
  `max_per_turn`, so it reads as one a turn. The Great Work's third chapter is
  capped at one cast a turn.

A probe shows it: with The Great Work's grant live and two instants in the
graveyard, casting the first leaves the second uncastable.
`tests/unit/casting/test_graveyard_cast_grant.py` and
`tests/unit/casting/test_spells_cant_be_countered.py` each cast one card under
a flashback permission and never a second, so nothing holds the cap either way.

## The change

1. The static's compile writes `max_per_turn: None` for a `grants_flashback`
   static with no printed cap, beside the escape and retrace cases.
2. `op_grant_graveyard_cast` writes `max_per_turn: None` for a
   `grants_flashback` grant that prints no `max_per_turn`, the same explicit
   `None` its `unmetered` flag writes.
3. The comment on `casting._permission_reaches` names flashback among the
   uncapped permissions, and the row in
   [rules-coverage.md](../rules-coverage.md) says a flashback permission is
   uncapped because its exile is the brake.

It changes no printed cap: a permission that prints `max_per_turn` keeps it.
It also leaves alone which permission a cast is billed to when two cover the
same card (`casting._graveyard_cast_permission`, first unspent wins).

## Gate

A unit test under `tests/unit/casting/` for the uncapped flashback permission:
with two instants in the graveyard, casting the first under The Great Work's
grant exiles it and leaves the second castable, and the same holds under a
Lier-shaped static (`t_lier` in `tests/data/uncounterable_static.cards.json`).
A permission that prints `max_per_turn: 1` beside `grants_flashback` still
allows one cast. `tests/cards` re-verifies Lier, Return the Past and The Great
Work through the six gates, and `tests/cards/test_golden_pool.py` is re-pinned.

## Open questions

- **Re-pin and ship as a card behaviour change.** The fix changes how shipped
  cards play, so the golden pool pin moves. Recommended: ship it as a `fix(dsl)`
  pull request on its own, so the title says a card's play changed and the
  merge releases it.
- **Fix the static and the grant together.** They are the same misreading on
  two paths. Recommended: one pull request, since both rest on the same rule and
  one test file covers both.
