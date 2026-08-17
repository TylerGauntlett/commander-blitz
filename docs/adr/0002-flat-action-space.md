# ADR 0002 — A structured flat action index

**Status:** accepted

## Context

An RL policy needs a fixed-size action space. Magic offers a different set of legal
actions in every state, ranging from one ("pass") to dozens.

## Decision

A fixed index of 1025 actions, carved into **structured** ranges: a slot per hand
position, per battlefield position, per ability, per target option. Slots are assigned
by a deterministic, stable sort (hand by mana value → card id → oid; battlefield by
type group → card id → oid).

**The size has moved once, deliberately.** It was 825 until planeswalkers became
attackable: a planeswalker is a third kind of thing a creature may attack (506.2),
so it needs a defender slot, and `DEF_CAP` rose from 3 to 8. Attack-target slots
are keyed by a *tagged* id — `("player", pid)` or `("pw", oid)` — because a player
id and an object id are both ints and 1 is a legal value of each, so an untagged
map would let "attack player 1" and "attack the planeswalker whose oid is 1"
collide on one slot. Players come before planeswalkers so a seat's slot does not
move when a planeswalker enters or dies mid-declaration.

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

**Cost of reversing.** Low in code -- the table is built in one function and the
caps are constants -- and high in training. Any change to a cap below `IDX_KEEP`
shifts every index above it, so every checkpoint trained against the old layout has
the wrong head shape and must be retrained. `tests/ai/test_action_space.py` pins the
literal size for exactly that reason: the number should never move without somebody
deciding that it should.

## Alternatives considered

**"The nth legal action" over a padded list.** Trivial to build, and it was rejected
because the semantics of an index change every step — the policy would have to relearn
the mapping continuously.

**A tree- or language-structured action space.** More expressive, and much more machine
to build and debug. Not worth it at this size.
