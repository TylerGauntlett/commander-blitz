# ADR 0003 — The engine taps your lands for you

**Status:** accepted

## Context

Paying a cost means choosing which sources to tap. With ten permanents that is a
combinatorial choice, and it is a *separate* decision from "what do I want to cast" —
but the rules interleave the two.

For an agent this multiplies the branching factor enormously. For a human it is the
most tedious part of playing online.

## Decision

An `Action` carries no payment. Legality only offers a cast or activation when
`solve_payment()` can find a set of sources to tap; applying it runs the same solver
and taps them.

The solver satisfies coloured pips first, most-constrained colour first, then pays
generic from the **most abundant** colours — measured across the player's whole mana
base, not the shrinking remainder. A bounded backtracking search catches cases greedy
alone would strand.

## Consequences

**Good.** The action space collapses to "what do I cast", not "what do I cast and how
do I pay". The abundance heuristic means the engine does not tap your only Forest to
pay a generic cost and then leave you unable to cast a green spell — the most common
way naive auto-payment plays visibly badly, and a case covered by a test.

**Bad.** You cannot deliberately tap the "wrong" land to bluff or to play around a
land-destruction effect. Neither deck contains a card that punishes this.

**Cost of reversing.** Low by design. `Action` already reserves a `payment` field; a
manual-tap mode would add actions to legality without changing anything else.

## Alternatives considered

**Make payment an explicit sequence of decisions.** Fully general and correct.
Rejected: it would roughly double the number of decisions per turn, most of them
forced, and both the human UX and the RL sample efficiency would suffer badly.

**Greedy payment with no ordering heuristic.** Simplest, and rejected because it
strands colours often enough to be noticeable within a few turns.
