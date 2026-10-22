---
id: selection-model
title: One selection model
area: play
effort: M
impact: high
why: every decision in every game, on every device
depends_on: []
status: proposed
---

## Today

Pressing a permanent with several abilities asks
which one in a modal (`AbilityMenu`); a Treasure asks which colour the same
way. Proliferate, "any number of target permanents" and the other pick-several
decisions are answered as rows in the action panel with a commit slab
(`PickRows`), and the board's cards toggle those rows. Targets are chosen on
the board. Modes, X and yes-or-no are dialogs. Many options with no card face
are a `ChoiceCombo`. Every one of these was the right call for the decision
it was built for, and together they are five shapes for what a player
experiences as one question: *which of these things do I mean?*

## The change

**The rule to converge on:** a choice among things on the table is made on
the table, staged, and committed once; a choice among things that are not on
the table is made in the panel or a dialog; and the panel remains the
universal fallback under which every legal action is one control exactly once
([ADR 0015](../adr/0015-every-legal-action-is-one-control.md)). Attack
declaration already follows the rule, and `PickRows` already borrowed its
shape; what is left is to make the board the primary surface for every
object pick and the panel the mirror, with one staged set in `uiStore` and
one commit control (`logic/commit.ts`) rather than a set per surface.

**Do it as an audit before it is done as code.** A table of every
`PendingDecision` kind and purpose against the surface it uses today and the
surface the rule gives it, kept beside `Journeys.stories.tsx` with a press
budget per decision, is the deliverable of the first pull request; the
budgets are what make "unified" measurable and what stop a later surface
from drifting back. The phone modality adds a touch column to the same
table, which is why it waits for this.

**Smaller items in the same pass:**

- `B` always backs out of a staged set, everywhere, and never discards a set
  the player cannot rebuild in one press.
- The targeting hint says why a card is skipped; the same hint for a card
  that cannot be *cast* (mana, timing, a cast lock) and an ability that cannot
  be activated, read from the engine's own reason where it has one.
- The stack: a response to a response is a stack of three and the panel is
  the only place that reads it in order.
- `UI-02` in [TECH_DEBT.md](../../TECH_DEBT.md), the accessibility pass,
  because every surface this touches is one of the ones it lists.

## Gate

The audit table itself, held by a test that every `PendingDecision` kind the
engine can emit has a row; a journey with a press ceiling per decision kind
in `Journeys.stories.tsx` and the handheld e2e journeys; and the existing
one-control-per-action invariant, which must hold through every surface the
pass touches.
