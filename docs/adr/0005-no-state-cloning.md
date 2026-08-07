# ADR 0005 — Replay instead of state snapshots

**Status:** accepted

## Context

Undo, environment resets and any lookahead search all want the same thing: a way to
get back to an earlier position. The obvious answer is to deep-copy `GameState`.

Cloning a rules engine's state is a notorious source of bugs. Every new field is a new
chance to forget it in the clone, and the resulting failure is silent — the game keeps
running, just slightly wrong.

## Decision

Never clone. The engine is deterministic (all randomness routes through `state.rng`),
so **seed + action tape fully determines a position**. Undo replays from the seed minus
the last human action. The env resets by building a new game.

## Consequences

**Good.** There is no clone to get wrong. The event log doubles as the replay tape and
as the play-by-play the UI shows. Golden tests are just recorded tapes. A whole
category of bug does not exist.

**Bad, and it is a real cost.** Agents cannot search. The heuristic agent is reflexive
— it scores actions from the current position with no lookahead — because exploring a
hypothetical would mean replaying a whole game per node. An MCTS agent would need this
decision revisited first.

Undo is O(game length), which is irrelevant for a local app and would not be for a
search.

## Consequences for correctness

This is also what makes the determinism guarantee testable rather than aspirational: if
replay ever diverged, undo would visibly break, and
`test_event_logs_match_for_identical_seeds` would fail.

## Alternatives considered

**Deep-copy on demand.** Standard, and enables search. Rejected for an MVP because the
correctness risk is invisible and permanent, while the cost of not having search is
visible and bounded (a weaker AI).

**Copy-on-write / persistent data structures.** Gets both, at the price of restructuring
every mutation in the engine. Too large a bet this early.
