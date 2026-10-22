---
id: brackets
title: Brackets, derived from the list
area: matchmaking
effort: M
impact: medium
why: a filter and a signal on every tile; the precondition for the queue
depends_on: [official-precons]
status: proposed
---

## Today

Nothing on a tile or in a dossier says how strong a deck is beyond the
editorial ratings a person wrote for a shipped deck, and an import has none.
The Commander Brackets, one to five, are defined by what a list contains:
Game Changers, mass land denial, chained extra turns, two-card infinite
combos, and tutors, with the thresholds per bracket set by the format's own
rules and revised by its stewards from time to time.

## The change

Most of a bracket can be read off a deck at request time, beside the curve,
so it cannot drift:

- a hand-kept `data/catalog/game_changers.json`, with the same discipline as
  `art_pins.json`: a named list, a test that every entry resolves in the
  catalog, and a note on where the list comes from;
- counts over the list for extra turns, tutors and land destruction, from
  oracle text and the engine's own vocabulary where a card is native;
- a hand-kept table of two-card combos, from the community's combo database,
  which the arena can go on to verify as the pairs become native.

The derived bracket is a suggestion, because the format defines a bracket as
a conversation, not a measurement, and an editorial `bracket` on a shipped
deck overrides it where the heuristic misreads a list. It is shown on the
tile and in the dossier, filters the shelf, and is what the queue matches
on. It waits on the precon data model because the deck file's fields and
the shelf's filters are settled there.

## Gate

A test that every Game Changer and every combo entry resolves in the
catalog; `deckinfo.py` tests pinning the bracket each shipped deck derives;
and the shelf's filter in a story and the e2e catalogue spec.
