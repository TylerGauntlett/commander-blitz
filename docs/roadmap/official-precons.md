---
id: official-precons
title: The real precons
area: decks
effort: L
impact: high
why: the shelf's main promise, and the driver that orders the card work
depends_on: [art-store]
status: proposed
---

## Today

The shelf's "Precons" segment holds twelve decks, and all but two
are lists the maintainer likes, promoted from Moxfield. The word is doing
work it cannot do: a player who filters to precons expects the decks Wizards
sells, and a deck somebody built is a different promise. Every shipped deck
costs a hand-written dossier, a strategy module with a page, a whole-game
test and its art, and each of those is held by a test that fails without it.

## The change

**Target.** The shelf ships the official Commander preconstructed decks from
the last five years, a window the sources manifest names as one constant so
it is a rolling window and not a list that goes stale, and nothing else under
that word. The lists the maintainer likes stay shipped,
under a word that is true of them: **Favorites**.

**Sources.** Official lists are published data, not something to scrape:
MTGJSON's deck files carry every preconstructed deck with its set, release
date and the exact printings, and Moxfield mirrors the same lists under its
own precon section. The manifest, `data/decks/sources.json`, is one row per
precon with the set, the release date, the product name and the source URL,
generated from the deck files and filtered to the window, so widening it is
a change to one constant and a run of the script, and a set ageing out of
the five years is the script reporting a row to retire. Five years of
Commander releases is on the order of a hundred decks, which is why the
data-model changes in the table below come before the first set. Printings
come with the list, which is what the per-seat `printings` design was built
for.

**What a shipped deck costs today, and what changes at dozens per year:**

| Requirement now | Held by | For the precon window |
|---|---|---|
| Every card native | the import pin test per deck | Unchanged, and it is what orders the card roadmap: each new precon set is a dated deadline for the mechanics it introduces |
| Tags, ratings, strategy, signature cards | `test_deck_metadata.py` | Keep the dossier editorial, since nothing in a list says a deck is hard to pilot, but seed the tags and the strategy paragraph from the product's own description, with a person's edit as the gate rather than a person's blank page |
| A CPU strategy module and a page under `docs/cpus/` | `test_registry.py` | A deck file declares an `archetype`, and `strategy_for` falls back deck id, commander, archetype, default. A module and a page are written where the archetype's plan visibly misplays the deck, and the test asks for a module or an archetype |
| Every precon through a whole four-player game | `test_deck_games.py` | A seeded sample per run, with the full matrix in the arena stage, which is already its own runner |
| Art for every printing the list chose | eager prefetch on the desktop | The owned art store; the content package carries the window's printings and fetches the rest |

**Favorites.** The site's most frequent player is its maintainer, and the
twelve are the decks that player wants at the table without pasting a link
every time. So they stay exactly where they are, in `data/decks/`, native,
with their strategies, their pages and their import pins, and the only
change is the word on the tile: `source` grows a `favorite` value beside
`precon` and `moxfield`, the deck file carries it, and the shelf's segments
become **Precons**, **Favorites** and **Yours**. The dossier, the ratings and
the signature cards stay editorial for a favorite, since they are the one
tier a person has actually written about. Promoting a personal import to a
favorite is the existing `promote_deck.py` with the source set, which is
how a thirteenth arrives.

The same word works for a player's own imports: a star on a tile in
**Yours** that pins the deck to the top of that segment, kept on the server
beside the import so it survives a reload, which is one field on the
generated deck file. It is a small thing, and it is the thing the segment
is for once the imports outnumber the shelf.

**The shelf at dozens.** `DeckCatalog` is a grid with search, colour pips, a
source filter and a cycling sort. For the window it needs: grouping by set
with the release as the order, so the newest precons are the first row; an
archetype filter; the bracket filter; and group headers as regions so the
grid stays walkable with a pad rather than being one long sweep. The floors
of [ADR 0013](../adr/0013-handheld-floors-are-ci-gates.md) apply to every
tile.

Deliver it in that order: the data model first (the `favorite` source, the
`archetype` fallback, the manifest and its script, the sampled game test),
then one set at a time, newest first, each set driving the card loop until
its lists are native before it is promoted.

## Gate

The manifest script's window is one constant and a test asserts every row
in it is inside the window and every deck under `precon` has a row; the
import pin per deck; `test_registry.py` accepting a module or an archetype;
the shelf's story and e2e specs at the handheld floors with the window's
tile count; and the favorites segment's story with the twelve in it.
