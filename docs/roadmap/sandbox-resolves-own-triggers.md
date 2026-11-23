---
id: sandbox-resolves-own-triggers
title: The authoring sandbox resolves a card's own triggers
area: cards
effort: M
impact: medium
why: a card whose enters trigger sits under a castable ability, such as a Vehicle with crew, cannot prove its trigger, so Night Scythe in the Necron Dynasties precon waits on it
depends_on: []
status: proposed
---

## Today

Gate 5 of the authoring pipeline casts the card in a sandbox and measures the
board against its expectation. `cards/authoring/verify.py::drive` answers
every decision until the card is done, and treats any `PRIORITY` decision as
"done" (`_NOT_OUR_BUSINESS`): priority is taken to mean the card has finished
resolving. The engine only asks for priority when passing is a choice
(`engine/game.py::_should_auto_pass`). One such window is a non-empty stack
while its player holds an activated ability they can pay for.

So a permanent whose own enters trigger goes on the stack while it offers a
payable activated ability is measured with that trigger still unresolved.
Crew (`tap_permanents` with `total_power`) is the common case: the sandbox's
creatures can pay it. Night Scythe ("When this Vehicle enters, create a 2/2
black Necron Warrior artifact creature token", Crew 2) fails gate 5 with "0
tokens, expected 1". Its gap record is `data/authoring/gaps/night_scythe.json`,
capability `sandbox_resolve_own_triggers`. The same card without crew creates
the token.

Shipped cards of this shape pass only because their expectations measure the
board before the trigger: Thunderhawk Gunship, Esika's Chariot and Aethersphere
Harvester in `data/cards/auto/expectations.json` assert only the zone and the
pre-trigger permanent count. Their triggers are therefore unproven by gate 5.

## The change

1. In `drive`, a `PRIORITY` decision with the card's own triggered ability on
   top of the stack passes priority instead of returning, until the stack
   holds nothing the card put there. Every other priority window still ends
   the drive, and the turn-boundary stop is unchanged.
2. Re-measure every shipped card whose outcome changes, and strengthen its
   expectation to what the trigger now visibly does. This is the bulk of the
   work: no expectation may be loosened, and a card whose trigger now shows it
   doing the wrong thing is a bug fixed in the same pull request.
3. Harvest Night Scythe, which finishes the Necron Dynasties precon; see
   [precon-40k-necron-dynasties](precon-40k-necron-dynasties.md).

It does not make the sandbox attack, block or activate abilities. A trigger
that needs combat stays the weak fallback the worker brief allows.

## Gate

A unit test under `tests/unit/authoring/`: a test-pool Vehicle with an enters
trigger and a payable crew is measured after its trigger resolves, while a
card with no trigger of its own still stops at its first priority window. Then
`tests/cards` over the whole pool, with the strengthened expectations, and
Night Scythe's six gates.

## Open questions

- **Which triggers the sandbox resolves.** Recommended: only triggered
  abilities whose source is the card under test. Resolving everything on the
  stack would fold the dummy board's own triggers into every card's outcome,
  which is what `drive` stops at priority to avoid.
- **The re-measure.** Recommended: one pull request that strengthens every
  changed expectation through `--collect`, run per affected card, rather than
  loosening any. If the changed set turns out large, phase it: the harness
  change with the cards it touches first, then Night Scythe.
