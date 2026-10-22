---
id: stack-in-order
title: The stack reads in order from the panel
area: play
effort: S
impact: medium
why: every response to a response, which is the skill the format is about
depends_on: []
status: proposed
---

## Today

`StackPanel` draws the stack as a pile of faces, top first, with the
targeting relationship drawn by `CombatArrows`; a press on a ply is a target
when a spell is waiting for one and otherwise a read
(`useTableGestures.onStackItem`). At the handheld size the pile is a rail
panel the ring can land on but cannot read in order: a stack of three is
three faces offset by `PLY_Y`, the two below the top are mostly covered, and
the only text that says what resolves next is on the face itself. The
action panel, which is the one surface every decision can be answered from
([ADR 0015](../adr/0015-every-legal-action-is-one-control.md)), says nothing
about the stack at all: a priority window with three items on the stack is
drawn the same as one with none, so the player responding to a response
reads the order off a pile of art.

## The change

The panel is the one place the stack is read in order, and the pile is the
picture of it.

- **A stack strip in the panel.** While `state.stack` is non-empty on a
  priority window, the panel's head carries one line per item, top first,
  in the words the log already uses for the same item (`logic/events.ts`
  names a stack item the way the ticker does), each naming its controller
  and its targets, with "resolves next" on the first. Lines, not stops: the
  strip is read, and the pile remains the thing to press.
- **The pile stays the pile.** `StackPanel` is unchanged except that
  pressing a ply while nothing is being targeted sends the ring to the
  strip's matching line, so a controller can read a buried item without
  uncovering it.
- **Nothing changes size with game state**
  ([ADR 0016](../adr/0016-nothing-changes-size-with-game-state.md)): the
  strip is a fixed number of lines, and a stack deeper than that scrolls
  inside it rather than growing the panel.

What it does not do: change what the engine puts on the stack, or add an
action. A response is still the cast or activate action the panel already
carries.

## Gate

A `StackPanel` story and a panel story with a stack of three, each at the
handheld floors, asserting the strip reads top first and that the panel's
box is the same height as with an empty stack. A journey in
`Journeys.stories.tsx` that responding to a response costs no more presses
than responding to a spell, under the priority row's ceiling in
`decisionAudit.ts`.
