---
id: self-sacrificing-lands
title: A land that sacrifices itself on entering
area: cards
effort: S
impact: medium
why: the New Capenna Commander fetch-land cycle waits on it, and it alone keeps Cabaretti Cacophony and Blight Curse off the shelf
depends_on: []
status: proposed
---

## Today

The New Capenna Commander fetch lands (Cabaretti Courtyard, Riveteers
Overlook, Maestros Theater, Obscura Storefront, Brokers Hideout) print "When
this land enters, sacrifice it. When you do, search your library for a basic
… card, put it onto the battlefield tapped, then shuffle and you gain 1
life." The DSL already says it: a `self_enters` trigger that sacrifices
`self_only`, then a `reflexive_trigger` that fetches and gains life. What
refuses it is gate 4 of `cards.authoring.verify`: `_play_once` allows a
permanent to end only on the battlefield (an Aura also in the graveyard), and
these lands end in the graveyard as printed.
`tests/cards/test_authoring.py::TestASelfLegalTriggerIsExercisedAgainstTheBoard::test_a_permanent_that_genuinely_vanishes_is_still_rejected`
pins that a creature whose text is "When this creature enters, sacrifice it."
must still fail, so admitting the lands widens a gate, and that is the
owner's call. The gap records are `cabaretti_courtyard`, `maestros_theater`,
`obscura_storefront` and `riveteers_overlook` under `data/authoring/gaps/`,
all naming `self_sacrificing_permanent_gate`. The same question is open on
[precon-ecc-blight-curse](precon-ecc-blight-curse.md), whose last card is
Riveteers Overlook.

## The change

1. Gate 4 admits the graveyard for a permanent whose unconditional
   `self_enters` trigger opens by sacrificing `self_only` and goes straight
   on to a `reflexive_trigger`, the way it admits an Aura; the check reads
   the compiled card, not the oracle text.
2. The expectation for such a card has to assert what the reflexive half did
   (the fetched land on the battlefield, the life gained), which a card that
   merely vanished cannot.
3. Harvest: the cycle's cards by name through `/author-cards`, and their gap
   records retired.

It does not widen gate 4 for any other shape: a permanent that sacrifices
itself with no reflexive half, or on a condition, still fails.

## Gate

The pinned vanishing-creature test unchanged and still green; a new test in
`tests/cards/test_authoring.py` beside it that a self-sacrificing land with a
reflexive fetch clears all six gates, and that the same land with the
reflexive half removed is still rejected at gate 4; the harvested lands'
six gates.

## Open questions

- **May gate 4 admit the graveyard for this one shape?** Recommended: yes,
  narrowed to a `self_enters` trigger with no condition whose first effect
  sacrifices `self_only` and whose next is a `reflexive_trigger`, so the
  pinned vanishing creature, which has no reflexive half, still fails and
  nothing else the gate catches moves.
- **Does Blight Curse take its answer from here?** Recommended: yes; the
  question on precon-ecc-blight-curse is this one, so answering it here and
  adding this item to that precon's `depends_on` keeps one owner for the
  decision.
