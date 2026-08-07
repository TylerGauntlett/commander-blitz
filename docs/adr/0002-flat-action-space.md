# ADR 0002 — A structured flat action index

**Status:** accepted

## Context

An RL policy needs a fixed-size action space. Magic offers a different set of legal
actions in every state, ranging from one ("pass") to dozens.

## Decision

A fixed index of 825 actions, carved into **structured** ranges: a slot per hand
position, per battlefield position, per ability, per target option. Slots are assigned
by a deterministic, stable sort (hand by mana value → card id → oid; battlefield by
type group → card id → oid).

The mask is built by walking `legality.legal_actions()` and encoding each result.

## Consequences

**Good.** Index 37 tends to mean the same *kind* of thing across steps, which is far
more learnable than "the 37th legal action" — that shuffles whenever the board changes.
Because the mask is *derived from* the legality enumeration rather than reimplementing
it, the mask, the HTTP action list and what `Game.apply` accepts cannot drift apart.

**Bad.** Actions can fall outside the layout — a 21st card in hand, a 5th target
option. They are dropped from the agent's view. To keep that from being invisible,
`ActionTable.dropped` records them and a test asserts
`len(by_index) + len(dropped) == len(legal_actions)`.

**Cost of reversing.** Low. The table is built in one function; the caps are constants.

## Alternatives considered

**"The nth legal action" over a padded list.** Trivial to build, and it was rejected
because the semantics of an index change every step — the policy would have to relearn
the mapping continuously.

**A tree- or language-structured action space.** More expressive, and much more machine
to build and debug. Not worth it at this size.
