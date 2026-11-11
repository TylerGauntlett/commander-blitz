---
id: rad-counters
title: Rad counters
area: cards
effort: M
impact: medium
why: every rad-counter card in the Fallout precons waits on it, Acquired Mutation and Megaton's Fate among them
depends_on: []
status: proposed
---

## Today

A player's counters are the kinds in `player.PLAYER_COUNTER_KINDS`, which
lists poison and energy only; the comment above it names rad as one of the
kinds that would need a field on `PlayerState` and an entry there. Each kind
has its own funnel in `primitives` (`add_poison`, `add_energy`), and
`ops_combat_flags` (proliferate) and `ops_life.op_lose_all_player_counters`
walk `PLAYER_COUNTER_KINDS`, so a new kind reaches both once it is listed and
funnelled. "Lose all counters" takes every kind at once; nothing removes one
named kind from a player.

Rad counters are more than a kind: a player with any has an inherent
triggered ability at the beginning of their precombat main phase, which
mills that many cards, then loses 1 life and removes one rad counter for
each nonland card milled. The engine already has the two shapes this needs:
`turn.begin_step`'s `Step.PRECOMBAT_MAIN` branch runs `sagas.turn_based_lore`
and fires `EventType.PRECOMBAT_MAIN`, and `turn._monarch_draw` is a sourceless
inherent trigger the game controls, resolved inline rather than on the stack.
[rules-coverage.md](../rules-coverage.md#not-implemented) does not mention rad
counters at all.

So no card can give a player a rad counter, and none can remove them. The
Scrappy Survivors precon found it through Acquired Mutation and Megaton's
Fate, and Hail, Caesar through Survivor's Med Kit; their gap records are
`data/authoring/gaps/acquired_mutation.json`, `megaton_s_fate.json` and
`survivor_s_med_kit.json`.

## The change

1. `rad` joins `PLAYER_COUNTER_KINDS`, with a field on `PlayerState`, an
   `add_rad` funnel in `primitives` in `add_energy`'s shape (counter
   replacements applied, then an event of its own), and a key beside poison
   and energy in the player's serialized view.
2. An op that gives a player rad counters ("defending player gets two rad
   counters", "each player gets four rad counters"), in the shape of
   `add_energy`, reaching a trigger's defending player and `for_each_player`.
3. The rad trigger at the beginning of the precombat main phase of a player
   who has rad counters: mill that many, then for each nonland card milled
   lose 1 life and remove one rad counter, through the existing mill and
   life-loss funnels so their replacements and triggers still apply.
4. A way to remove every counter of one named kind from a target player
   ("target player loses all rad counters"), as an option on the existing
   lose-all-counters op rather than a second op.
5. Harvest: Acquired Mutation and Megaton's Fate through `/author-cards`,
   then the catalog's other rad cards in one wave. Survivor's Med Kit also
   needs "choose one that hasn't been chosen", which this item does not
   build.

It adds no other player counter kind (experience is
[its own item](experience-counters.md), ticket is unplanned) and no client
surface beyond the existing player-counter readout.

## Gate

A unit test under `tests/unit/` for rad counters: the op adds them to the
named player and to each player, the precombat-main trigger mills that many
and costs 1 life and one counter per nonland card milled (a land-only mill
costs nothing and leaves the counters), it does not fire for a player with
none or on another player's turn, proliferate adds one to a player who has
any, and losing all rad counters leaves poison and energy alone. Acquired
Mutation's and Megaton's Fate's six gates pass, and the generated DSL
reference (`tests/cards/test_dsl_reference.py`) lists the new op.

## Open questions

- **How the counter is stored.** A field of its own on `PlayerState` beside
  `poison` and `energy`, or a general `counters` mapping? Recommended: a
  field of its own, the shape the two existing kinds have and the one
  [experience counters](experience-counters.md) recommends, so the change
  stays additive.
- **On the stack or inline.** The printed rule makes the rad trigger a
  triggered ability that uses the stack, so players can respond with the mill
  pending. `_monarch_draw` resolves its sourceless trigger inline and records
  that as a divergence. Recommended: on the stack, as the rules say, because
  a player who sees the mill coming can sacrifice a Food or cast an instant
  first; inline only if the engine has no seam for a sourceless trigger on
  the stack, and then recorded as a deliberate divergence in
  rules-coverage.md beside the monarch's.
- **Where the client shows it.** Recommended: the same player-counter readout
  that shows poison and energy, hidden at zero, with no new component; a
  surface beyond that would need its story and floor (ADR 0013).
- **Is it an ADR.** Recommended: no; it is one more player counter kind under
  an existing rule, and its line goes into the implemented table in
  rules-coverage.md. An ADR only if the stack question is answered with a
  new seam for sourceless triggers.
