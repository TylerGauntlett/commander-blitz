---
id: precon-sets
title: Every precon set in the window
area: decks
effort: L
impact: high
why: each set is a shelf row a player expects and a dated deadline for the card work
depends_on: [official-precons]
status: proposed
continuous: true
---

## Today

The manifest, `data/decks/sources.json`, lists every official Commander
precon inside the window `scripts/sync_precons.py` names as one constant,
and `official-precons` ships the newest set in it. Every other row is a deck
the shelf promises and does not have: its list is published, its printings
are known, and some of its cards are not native, which the import pin
would show the day the deck file is written.

## The change

One batch is one set from the manifest, the newest not yet shipped first.
The batch drives `/author-cards` (and `/extend-dsl` for a mechanic the DSL
lacks) until every list in the set is native, then writes each deck file
with `source: precon`, its `set` and release, an `archetype` and an editorial
dossier seeded from the product description, and the import pin that holds
it. A deck gets a strategy module and a page under `docs/cpus/` only where
its archetype visibly misplays it. A set the window ages out is the script
reporting a row to retire, and its decks leave the shelf in the same batch.

## Gate

Per batch: the import pin of every deck in the set; the manifest test
(every row inside the window, every `precon` deck has a row) still green;
the sampled whole-game test drawing from the new decks; and the shelf's e2e
catalogue spec with the new release group in it.
