# ADR 0001 — Fixed-order continuous effects instead of the layer system

**Status:** accepted

## Context

Magic resolves continuous effects through seven numbered layers, with timestamps
inside each layer and a dependency-resolution pass on top. It exists because effects
can genuinely depend on each other: an anthem that pumps creatures with power 3 or
greater has to know what another anthem already did.

Implementing it properly is a substantial subsystem, and it is entangled with
everything — combat, targeting, state-based actions all read derived characteristics.

## Decision

Apply continuous effects in a **fixed order**:

```
printed -> subtype grants -> keyword grants -> P/T setting
        -> P/T modifying (anthems) -> counters -> until-end-of-turn pumps
```

and impose one constraint, checked at load time:

> A static ability's filter may not read another static ability's output.

Static filters match against printed characteristics plus the object's own board state
(controller, tapped, attacking). Results are cached against a version counter that
every mutating primitive bumps.

## Consequences

**Good.** No recursion is possible, so no dependency pass and no timestamps are needed.
The whole of `characteristics.py` is about 200 lines and is easy to reason about. The
cache is a single integer comparison.

**Bad.** A card whose anthem depends on another anthem's result cannot be expressed.
`loader.py` rejects one rather than accepting it and computing something wrong — which
is the important part: the limitation is enforced, not merely documented.

**Cost of reversing.** Moderate and contained. `chars()` is the only reader; replacing
its body with a real layer system would not change any caller.

## Alternatives considered

**Implement the layers properly.** Correct, and the right answer for an engine aiming
at full rules coverage. Rejected for an MVP: it changes no outcome for any card in the
two shipped decks.

**Recompute naively and hope.** Rejected — it produces wrong numbers silently, which is
the worst failure mode a rules engine has.
