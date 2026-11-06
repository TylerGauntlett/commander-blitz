---
id: experience-counters
title: Experience counters
area: cards
effort: M
impact: medium
why: every experience-counter commander waits on it, Meren of Clan Nel Toth and Ezuri, Claw of Progress among them
depends_on: []
status: proposed
---

## Today

A player's counters are the kinds in `player.PLAYER_COUNTER_KINDS`, which
lists poison and energy only. Each kind has its own funnel in
`primitives` (`add_poison`, `add_energy`), its own field on `PlayerState`,
its own event (`EventType.ENERGY_ADDED` for energy) and its own readers: `values` reads poison through `max_poison_of`, and
`Cost.pay_energy` spends energy. `ops_combat_flags` (proliferate) and
`ops_life.op_lose_all_player_counters` walk `PLAYER_COUNTER_KINDS`, so a new
kind reaches both once it is listed and funnelled.
[rules-coverage.md](../rules-coverage.md#not-implemented) lists "Experience
counters (122.1)" as not implemented.

So no card can give a player an experience counter or read how many they
have. Meren of Clan Nel Toth, the Sultai Arisen precon's card that found it,
does both; its gap record is `data/authoring/gaps/meren_of_clan_nel_toth.json`.
The catalog's other experience-counter cards (Ezuri, Claw of Progress,
Mizzix, Kalemne, Daxos, the Avatar benders) are the same two sentences.

## The change

1. `experience` joins `PLAYER_COUNTER_KINDS`, with a field on `PlayerState`,
   an `add_experience` funnel in `primitives` in `add_energy`'s shape (counter
   replacements applied, then an event of its own), and a key beside poison
   and energy in the player's serialized view.
2. An op that gives a player experience counters ("you get an experience
   counter"), in the shape of `add_energy`.
3. A value that reads a player's experience counters ("the number of
   experience counters you have"), usable wherever a value is, in a
   condition comparing a card's mana value with it (Meren) and in an
   amount (Ezuri).
4. Proliferate and "lose all counters" pick the kind up through
   `PLAYER_COUNTER_KINDS`; a test pins that they do.
5. Harvest: Meren, then the catalog's other experience-counter cards through
   one `/author-cards` wave.

It does not add any other player counter kind (rad, ticket), and nothing
spends experience counters, because no card does.

## Gate

A unit test under `tests/unit/` for experience counters: the op adds them,
the value reads them, a mana-value comparison against them resolves both
ways, proliferate adds one to a player who has any, and losing all counters
removes them. Meren's six gates pass, and the generated DSL reference
(`tests/cards/test_dsl_reference.py`) lists the new op and value.

## Open questions

- **How the counter is stored.** A field of its own on `PlayerState` beside
  `poison` and `energy`, or a general `counters` mapping on the player that
  poison and energy later move into? Recommended: a field of its own, the
  shape the two existing kinds have, so the change stays additive and the
  general mapping is its own refactor if a fourth kind ever arrives.
- **Where the client shows it.** Recommended: the same player-counter readout
  that shows poison and energy, hidden at zero, with no new component; a
  surface beyond that would need its story and floor (ADR 0013).
- **Is it an ADR.** Recommended: no; it is one more kind under an existing
  rule (122.1), and its line moves from "not implemented" to the
  implemented table in rules-coverage.md.
