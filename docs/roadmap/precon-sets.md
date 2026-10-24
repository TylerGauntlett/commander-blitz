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
precon inside the window `scripts/sync_precons.py` names as one constant.
Wretched Ranks ships; every other row is a coming-soon shell on the shelf,
served by `GET /api/precons/upcoming` until its deck file loads. The cards a
row lacks are `sync_precons.py --missing <id>`, and the newest set's are
already gap records in `data/authoring/gaps/`, so `docs/unsupported-cards.md`
ranks the capabilities they wait on. A whole set at a time proved the wrong
unit: Foundations Commander's other four decks need dozens of capabilities
between them, while one deck needed five.

## The change

One batch is one precon from the manifest: the one fewest capabilities away
from native, newest first among equals. The batch drives `/author-cards` (and
one `/extend-dsl` run per capability the deck lacks) until `--missing` is
empty, then `--write-deck` writes the file with its printings and release, a
person writes the dossier and picks an `archetype`, and the deck joins
`PRECONS` in `tests/cards/test_deck_legality.py`, which puts it under the
import pin and the sampled whole-game test. Its shell disappears by itself. A
deck gets a strategy module and a page under `docs/cpus/` only where its
archetype visibly misplays it. A row the window ages out is the script
reporting a precon to retire, and its deck leaves the shelf in the same batch.

## Gate

Per batch: `tests/cards/test_precon_imports.py` over the new deck; the
manifest test (every row inside the window, every `precon` deck has a row)
and the coming-soon test (`tests/server/test_upcoming_precons.py`) still green;
and the sampled whole-game test able to draw the new deck.
