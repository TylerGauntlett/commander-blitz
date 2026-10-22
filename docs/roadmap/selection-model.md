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
the board. Modes and yes-or-no are dialogs (`PromptDialog`); so is a single
pick of an object, a library search or a player. X is a stepper in the panel
(`XStepper`), the one decision whose control changes which id the slab
carries. The opening hand is a screen of its own (`OpeningHand`), for both
halves of the mulligan. Many options with no card face are a `ChoiceCombo`.
Every one of these was the right call for the decision it was built for, and
together they are six shapes for what a player experiences as one question:
*which of these things do I mean?* Nothing records which decision uses which
shape, and nothing fails when a new surface moves one.

## The change

**The rule to converge on:** a choice among things on the table is made on
the table, staged, and committed once; a choice among things that are not on
the table is made in the panel or a dialog; and the panel remains the
universal fallback under which every legal action is one control exactly once
([ADR 0015](../adr/0015-every-legal-action-is-one-control.md)). Attack
declaration already follows the rule, and `PickRows` already borrowed its
shape.

**This item is the audit, done before the rule is done as code.** A table of
every `PendingDecision` kind and purpose against the surface it uses today
and the surface the rule gives it, with a press ceiling per decision, kept
beside `Journeys.stories.tsx` as a module the stories import their ceilings
from (`decisionAudit.ts`). The ceilings are what make "unified" measurable
and what stop a later surface from drifting back. The phone modality adds a
touch column to the same table, which is why it waits for this.

- **Kinds and purposes both.** `DecisionKind` is a closed enum; `purpose` is
  the open tag `effects/context.ask_objects` and its siblings stamp on a
  decision so agents and the client can branch without reading the prompt.
  The table has a row per kind, and per purpose of the kinds that carry one,
  and the test that holds it reads the enum and walks the engine's source
  for every purpose literal passed to an ask helper, so a purpose added
  without a row fails where it is added.
- **A ceiling per decision kind.** Each kind gets a journey counted in
  presses, in `Journeys.stories.tsx` where a fixture is honest and in the
  handheld e2e journeys where the server has to answer, under the ceiling its
  row holds. The number is measured at the Deck's panel, as every budget in
  that file is, and written down as a ceiling, never an exact count.

The code the rule asks for is its own items, each grounded in a row of this
table: `one-staged-set` for the board as the primary surface of every object
pick with one staged set and one commit control, and `B` backing out of a
set; `refusal-reasons` for the hint that says why a press is refused;
`stack-in-order` for the panel reading a stack of three in order. `UI-02` in
[TECH_DEBT.md](../../TECH_DEBT.md), the accessibility pass, stays a debt item
and is paid by whichever of those touches its surfaces.

## Gate

The audit table itself, held by a test that every `PendingDecision` kind the
engine can emit, and every purpose the engine stamps, has a row; a journey
with a press ceiling per decision kind in `Journeys.stories.tsx` and the
handheld e2e journeys, each reading its ceiling from the table; and the
existing one-control-per-action invariant, which must hold through every
surface the pass touches.
