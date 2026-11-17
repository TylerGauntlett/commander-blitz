---
id: tapped-target-template
title: "Target tapped creature" is not "enters tapped"
area: cards
effort: S
impact: low
why: a card whose trigger targets a tapped creature is authored entering tapped, so it is a weaker card than the printed one
depends_on: []
status: proposed
---

## Today

The authoring templates in `cards/authoring/templates.py` read the word
"tapped" in a printed line as the card entering tapped, so a packet's
`starting_point` for Harbinger of the Tides ("When this creature enters, you
may return target tapped creature an opponent controls to its owner's hand")
carried a `self_enters_tapped` replacement the card does not print. A worker
caught it there; Surrakar Banisher shipped with the same replacement in
`data/cards/auto/templates.cards.json`. Gate 5 cannot see it, because nothing
in the sandbox asserts the card's own tapped state.

## The change

1. The enters-tapped template matches only a line about the card itself
   entering tapped, never "target tapped …" or "tapped creature".
2. Every shipped card carrying `self_enters_tapped` whose printed text does
   not say it enters tapped is re-collected through `--collect`, never
   hand-edited.

## Gate

A unit test under `tests/unit/` that the template gives Harbinger of the
Tides' and Surrakar Banisher's lines no `self_enters_tapped`, and still gives
it to a card printing "This land enters tapped."; a test in `tests/cards`
that no auto card carries `self_enters_tapped` without "enters tapped" in its
oracle text.

## Open questions

- **Scope.** The template fix and the cards it mis-authored only, or an audit
  of every template keyword that can appear inside a target phrase?
  Recommended: this fix and its cards only; an audit is its own item.
