---
id: one-staged-set
title: One staged set
area: play
effort: M
impact: high
why: every pick of a thing on the table, in every game, on every device
depends_on: []
status: in_progress
---

## Today

`uiStore` holds three staged sets with three shapes: `stagedAttacks`
(attacker to defender), `stagedBlocks` (blocker to attacker) and `picked`
(option ordinals, keyed by `logic/pickSeveral.pickKey`). Each has its own
stage, unstage and clear, and `clearStaging` empties all three by name.
`logic/commit.ts` knows the two combat sets and names the one control each
ends at; the pick-several slab is a separate control the panel renders with
its own carrier (`pickCarrier`). A single `choose_objects` whose options are
permanents on the table, "sacrifice a creature" among them, is not staged at
all: `PromptDialog` draws it as a modal of card faces and the board does not
answer it, so the press that a handheld player makes on the board goes
nowhere for exactly the decision whose subject is the board. `B` backs out of
targeting and selection through `useTableVerbs.back`, but a staged attack,
block or pick is undone card by card and there is no level of the unwind for
"take the whole set back". The audit in `decisionAudit.ts` beside
`Journeys.stories.tsx` records, per decision, which of these surfaces each
pick uses today and which the rule gives it.

## The change

One staged set in `uiStore`, one commit control in `logic/commit.ts`, and
the board as the primary surface for every pick of a thing on the table,
with the panel as the mirror — the rule the audit converged on, built.

- **One set.** `staged` replaces the three: a map from the thing being
  staged (an attacker, a blocker, an option ordinal) to what it is staged as
  (a defender, an attacker, membership), keyed by the decision the way
  `pickKey` keys picks today, so a set never outlives its question.
  `stageAttack`, `stageBlock` and `togglePick` become one `stage` with the
  three call sites unchanged in meaning; `clearStaging` empties one thing.
  The key covers all three kinds, combat included: a staged attack lives
  exactly as long as the declaration it was staged for, and a key change
  mid-declaration empties it like any other set.
- **One commit.** `commitmentFor` names the control for a pick-several
  decision the way it names Attack and Block, so `X` commits a Clever
  Concealment from wherever the ring is, and `logic/verbs.ts` prints it
  through the same shared function.
- **The board answers a single object pick.** A `choose_objects` whose every
  option is a permanent the layout draws is answered by pressing the card.
  A pick of one is committed by that press, the ring already on the first
  option, so it stays inside `PickOneInTheDialog`; a pick of several is
  staged and committed once. The panel's rows are the mirror where the card
  is not drawn (an opponent's lane at the handheld size), the shape `PickRows` and
  the attack declaration already have. `PromptDialog` keeps every pick whose
  options are not on the table: a library search, a hand to bottom, a mode,
  a player. `isModalDecision` is where the split is decided, and
  `ownsDecision` keeps the panel standing down for exactly the decisions a
  modal still owns ([ADR 0015](../adr/0015-every-legal-action-is-one-control.md)).
- **`B` backs out of a staged set, everywhere.** One level of the unwind in
  `useTableVerbs.back`, between targeting and selection: a non-empty set is
  emptied, and the voice says so. The level never discards a set the player
  cannot rebuild in one press: a set the "all" mark would rebuild is backed
  out whole, a hand-built one is backed out one press per card, newest
  first.

What it does not do: change which actions the engine offers, or how `/choose`
takes a set. The engine's `choose` actions stay one pick each and the slab
stays the one control carrying an id for the set.

It ships as one pull request, the four parts as phased commits in the order
above: they share the store and `logic/commit.ts`, and a split would land the
same files twice.

The dependency is real: the audit's rule column is what says which pick moves
to the board and which stays a modal, and its press ceilings are what this
item must not exceed.

## Gate

`tests/uiStore.test.ts` on the one set: staging across the three call sites,
a key change empties it, `clearStaging` empties it. `tests/commit.test.ts`
naming the pick-several control, and `tests/verbs.test.ts` printing it. A
story in `Journeys.stories.tsx` per pick kind the board now answers, each
under the ceiling its row in `decisionAudit.ts` already holds, and a story
that `B` empties a staged set at every decision kind that has one. The
`PromptDialog` stories for every pick that stays a modal, unchanged.
`expectUniqueActionIds` through all of it, as `clarity.spec.ts` holds it
across a game.
