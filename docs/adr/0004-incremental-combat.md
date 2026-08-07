# ADR 0004 — Declaring attackers one at a time

**Status:** accepted

## Context

Declaring attackers is a single game action that chooses a *set*. With n untapped
creatures and d defenders there are (d+1)ⁿ legal declarations. Enumerating them for an
action mask is impossible past about six creatures.

## Decision

The engine models declaration **incrementally**: repeated `ADD_ATTACKER(creature,
defender)` actions followed by `FINISH_DECLARATION`. Each increment is validated on
its own. Restrictions that only make sense on the complete declaration — menace — are
checked at `FINISH_DECLARATION`, so intermediate illegal-looking states are allowed.

The HTTP layer exposes `POST /declare`, which takes a whole set and loops the
increments server-side.

## Consequences

**Good.** The mask stays exact and small: one entry per (creature, defender) pair
rather than one per subset. Human UX is unaffected — the client stages a full
declaration and confirms it in one request.

**Bad.** An agent spends several steps on one game action, and a partially-declared
state is a real state the engine can be in. A `/declare` request whose later pair turns
out illegal fails mid-loop, leaving the declaration decision open; the client can
submit a corrected set. Duplicate creatures in one request are rejected before anything
is applied.

**Cost of reversing.** Not worth reversing. The set-at-once form is recoverable from
the incremental one (the server already does it), but not the other way around.

## Alternatives considered

**One action per legal attack set.** Correct and unusable — the action space explodes.

**A fixed "attack with everything profitable" macro.** Small and fast, and rejected
because it takes the most interesting decision in Magic away from the player.
