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

## Open questions

- **Today no longer matches the code: the pile is not a rail panel.**
  `TablePlay` floats `StackPanel` over the play area at every size, in the
  grid cell `.play__mine` sits in, and the pile is only drawn while
  `state.stack` is non-empty. Each ply already wears a tag reading "next",
  "ability" and its controller's name; only the targets are missing as text
  (they are in `data-hint`, and drawn by `CombatArrows`). The
  `[data-compact] .rail--right .stackpanel` cap in `styles/handheld.css` styles
  a placement that no longer exists. Recommended: proceed on these facts,
  rewrite **Today** to match in the decide commit, and delete the dead
  handheld rule in the pull request, since the strip replaces what it was
  for.
- **Where do the strip's words come from?** `logic/events.ts` names no stack
  item: the log's words are `describeEvent` in `logic/labels.ts`, which names
  a `spell_cast` or `ability_triggered` event rather than a `StackItemView`,
  and `ActionPanel` already resolves a `stack` target ref to the item's name.
  Recommended: one pure `stackLine(state, item)` in `logic/labels.ts` beside
  `describeEvent`, reusing its name and target lookups and verb agreement
  (`You` for the viewer), with a unit test, so the strip and the log cannot
  drift apart; `StackPanel`'s own target string moves onto it too.
- **How many lines, and what fills the box when the stack is empty?**
  ADR 0016 reserves a slot at its full size, and the gate asserts the panel's
  box is the same height with and without a stack, but the strip shows only
  "while `state.stack` is non-empty". Recommended: three lines, drawn in
  `.acts__head` below the prompt on every priority window, reading `—` when the
  stack is empty, with `scrollbar-gutter: stable` and an inside scroll beyond
  three, so the strip's height is a constant and `.acts__list` never moves.
  The alternative, taking the strip's height out of `.acts__list` only while
  the stack is non-empty, keeps the box but moves every action under the ring.
- **Only on priority windows, or on every decision while the stack is
  non-empty?** A target pick for a counterspell, or a trigger's choice, is
  made with the stack in play too. Recommended: every decision while the stack
  is non-empty draws the strip, and every decision reserves its slot, since a
  slot that appears on some decision kinds and not others is the same jump
  ADR 0016 forbids.
- **"Lines, not stops", yet a ply press "sends the ring to the strip's
  line".** The ring can only stand on a stop, and a ply press outside
  targeting already opens the item in the reader (`holdCard` in
  `useTableGestures.onStackItem`), which reads a buried item without
  uncovering it. Recommended: keep the lines non-stops and keep the press a
  read; the press also marks the matching line (`aria-current`) while the
  reader is up, rather than moving the ring, so ADR 0015's one-control rule is
  untouched and the change to `StackPanel` is a highlight.
- **Which journey, and what is its ceiling?** `BUDGET` in `decisionAudit.ts`
  has no response journey; the priority row is held to `PassInOnePress` and
  `AimASpell`. Recommended: a new `RespondToAResponse` journey in
  `Journeys.stories.tsx`, on a stack of two with a counterspell in hand aimed
  at the top item, with the ceiling `AimASpell` already holds (the card, then
  the target), added to the priority row's `journeys`.
- **The phone?** On a phone the right rail is a sheet holding `ActionPanel`
  (`TablePhone.stories.tsx` holds it). Recommended:
  the strip is part of `ActionPanel`, so the phone gets it with no extra work;
  the gate adds the phone viewport to the panel story rather than a separate
  phone story.
