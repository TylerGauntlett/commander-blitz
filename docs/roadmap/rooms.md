---
id: rooms
title: "Rooms: two doors on one permanent, and the unlock action"
area: cards
effort: M
impact: medium
why: every Room card waits on it, and Endless Punishment cannot ship native without Spiked Corridor // Torture Pit
depends_on: []
status: proposed
adr: true
---

## Today

A Room (709.5) is one card with two doors, each with its own name, mana
cost and abilities. The engine knows `Room` only as an Enchantment subtype
(`enums.py`'s subtype table). The nearest shape is `CardDef.second_face`,
which a split card, an Adventure or a modal double-faced card uses: the half
that is cast is then the whole object, and nothing keeps two halves on one
permanent. Nothing records a door as locked or unlocked, nothing switches a
locked door's abilities off, and `legality.legal_actions` offers no special
action that pays a locked door's cost to unlock it; the closest special
action is `legality._turn_face_up_actions`, the one thing a face-down
permanent can do. No trigger event hears "when you unlock this door".

[rules-coverage.md](../rules-coverage.md) does not list Rooms at all. Spiked
Corridor // Torture Pit, in the Endless Punishment precon, is the card that
found it; its gap record is
`data/authoring/gaps/spiked_corridor_torture_pit.json`, under the `rooms`
capability.

## The change

1. The card shape. A Room card's definition carries both doors as faces,
   the way `second_face` names the other half, and the loader checks both
   are present and that the card is a Room.
2. Door state on the object: which doors are unlocked. Casting a door
   (`second_face`'s cast path, either half) puts the permanent onto the
   battlefield with that door unlocked and the other locked (709.5d).
   `characteristics` reads the permanent's name, mana value and abilities
   from its unlocked doors only (709.5e), so a locked door's abilities are
   off for every reader at once.
3. The unlock special action (709.5f): as a sorcery, pay a locked
   door's mana cost to unlock it. Offered by `legality.legal_actions` the
   way `_turn_face_up_actions` offers turning a permanent face up, without
   a new `ActionKind`, so the RL action space is unchanged. It does not use
   the stack.
4. A `door_unlocked` trigger event for "when you unlock this door", fired
   both when a door enters unlocked and when the special action unlocks it,
   and "fully unlock" (both doors unlocked) for the cards that print it.
5. The client: the unlock action is one control, exactly once
   ([ADR 0015](../adr/0015-every-legal-action-is-one-control.md)), and a
   Room shows which doors are unlocked; its story ships under the handheld
   floors ([ADR 0013](../adr/0013-handheld-floors-are-ci-gates.md)).
6. The ADR records the shape: one object with per-door state, read through
   `characteristics`, rather than two objects.
7. Harvest Spiked Corridor // Torture Pit (it also needs a Devil token and a
   noncombat-only `replace_damage`, each its own `/extend-dsl` run) and every
   other Room one `/author-cards` wave can then express.

It does not add the cards' own riders beyond the Devil token and the
noncombat-damage key the first harvest needs.

## Gate

A unit test under `tests/unit/` for Rooms: casting either half enters with
that door unlocked and the other locked; a locked door's static and
triggered abilities do nothing; the unlock action is offered only at sorcery
speed, only for a locked door, and only when its cost can be paid; unlocking
fires `door_unlocked` once; the permanent's name and mana value follow its
unlocked doors. A story per layout mode for a Room with one door locked,
under the floors. Spiked Corridor // Torture Pit's six gates pass and the
generated DSL reference lists the new event.

## Open questions

- **One object or two.** Model a Room as one permanent with per-door state
  read through `characteristics`, or as two linked objects? Recommended: one
  object, because the rules make it one permanent (709.5) and every reader
  of names, mana value and abilities already goes through `characteristics`.
- **The unlock action's kind.** A new `ActionKind`, or offered as an
  activation the way turning a face-down permanent face up is? Recommended:
  the face-up pattern, so the RL action space is unchanged.
- **Scope of the first pull request.** Rooms alone, or Rooms plus the Devil
  token and the noncombat `replace_damage` key so Spiked Corridor // Torture
  Pit ships in it? Recommended: plus both, since each is small and the card
  is the gate.

