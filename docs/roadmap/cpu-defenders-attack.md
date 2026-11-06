---
id: cpu-defenders-attack
title: The CPU attacks with defenders that may attack
area: cpus
effort: S
impact: medium
why: every game the Abzan Armor CPU plays leaves its whole board at home
depends_on: []
status: proposed
---

## Today

The engine lets a creature with defender attack under the
`attack_despite_defender` static and op (`player_statics.defender_waived`,
read by `combat.can_attack`), and makes a creature deal combat damage equal
to its toughness under `combat_damage_by_toughness`
(`combat.combat_damage_amount`). The CPU's board reading predates both:
`ai/strategy/board.py`'s `can_attack_soon` and `ready_attackers` treat every
creature with defender as unable to attack, and `power` sizes every attack,
so `lethal_on_board`, `crack_back` and `GoWide.attack_value` count a 0/4 wall
as a creature that deals nothing. Abzan Armor ships on the `go_wide`
archetype with Felothar the Steadfast as its commander, so its CPU declines
the attacks its whole deck is built to make. `HARMFUL_COUNTERS` in
`ai/agents/heuristic_agent.py` and `ai/strategy/decks/atraxa_praetors_voice.py`
lists only `-1/-1` and `stun`, so the CPU proliferates a `-0/-1` counter on
its own Wall of Roots.

## The change

The CPU reads the same two rules the engine applies, through the engine's own
answers rather than a copy of them ([architecture.md](../architecture.md)):

1. `board.can_attack_soon` and `board.ready_attackers` ask
   `player_statics.defender_waived` instead of the defender keyword alone.
2. A `board.combat_damage` helper returns `combat.combat_damage_amount` for a
   creature, and `lethal_on_board`, `crack_back`, `incoming_unblocked` and
   `GoWide.attack_value` size attacks with it instead of `power`.
3. `HARMFUL_COUNTERS` becomes a predicate over `objects.pt_counter` that
   names every counter kind lowering power or toughness, shared by both
   readers.

It adds no archetype and no deck strategy module.

## Gate

Tests under `tests/ai/`: a position with Felothar and a board of walls in
which the `go_wide` CPU declares the walls as attackers and counts their
toughness toward lethal; the same board without Felothar, where it declares
none; and a proliferate choice that leaves a `-0/-1` counter on its own
permanent alone.

## Open questions

- **Scope of the damage helper.** Should every power-based reading in
  `ai/strategy/` move to the helper, or only the attack and lethal readers
  named above? Recommended: only those named, since blocking and removal
  scoring read power for reasons this item does not change.
- **The Abzan Armor archetype.** Keep `go_wide`, or add a dedicated
  archetype once the board reading is right? Recommended: keep `go_wide`
  and measure first; a new archetype is its own item.
