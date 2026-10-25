---
id: precon-sets
title: Every precon native, one at a time, then every import
area: decks
effort: L
impact: high
why: each precon is a shelf row a player expects, and every list a player pastes is the same card work one deck at a time
depends_on: []
status: proposed
continuous: true
---

## Today

The manifest, `data/decks/sources.json`, lists every official Commander
precon inside the window `scripts/sync_precons.py` names as one constant.
A precon whose deck file loads ships; every other row is a coming-soon shell
on the shelf, served by `GET /api/precons/upcoming` until its deck file
loads. The cards a row lacks are `sync_precons.py --missing <id>`, and the
cards already attempted are gap records in `data/authoring/gaps/`, each
naming the capability it waits on, so `docs/unsupported-cards.md` ranks
those capabilities. A whole set at a time proved the wrong unit: Foundations
Commander's decks need dozens of capabilities between them, while one deck
needed five.

Everything that is not a shipped deck imports as a proxy that keeps its
keywords and loses its text ([deck-import.md](../deck-import.md)). The loop
that closes the gap is in place: the template tier, the agent tier behind
six gates, gap records, and `/extend-dsl` to clear them
([card-authoring.md](../card-authoring.md)). The queue is ordered by what
players have imported and then by EDHREC rank. Working that queue top down
spreads each batch across thousands of unrelated cards, so no batch ever
finishes a deck a player can pick.

## The change

**One batch is one precon taken to 100%.** The batch is the manifest row
fewest cards short of native, newest first among equals; a row whose
missing cards have never been through the queue goes through
`/author-cards` by name first, because until it has, its distance is
unknown. The batch:

1. Runs `/author-cards` by name over the row's `--missing` list, which
   either writes a card or files its gap record.
2. Clears every capability those gap records name, one `/extend-dsl` run
   and one commit per capability, in the order the most cards elsewhere in
   the catalog wait on it. A capability that needs a rules subsystem the
   engine does not have ([rules-coverage.md](../rules-coverage.md#not-implemented))
   stops the batch: it becomes its own item and the precon waits on it.
3. Re-authors the row's cards until `--missing` is empty, then
   `--write-deck` writes the deck file with its printings and release. A
   person writes the dossier and picks an `archetype`, and the deck joins
   `PRECONS` in `tests/cards/test_deck_legality.py`, which puts it under the
   import pin and the sampled whole-game test. Its shell disappears by
   itself.
4. Harvests the rest of the catalog the batch's capabilities unblocked: the
   template tier with `--retry`, then one `/author-cards` wave over the
   pending cards the new vocabulary reaches.

A deck gets a strategy module and a page under `docs/cpus/` only where its
archetype visibly misplays it. A row the window ages out is the script
reporting a precon to retire, and its deck leaves the shelf in the same
batch.

**After the window.** Once every row in the window is native, the unit stays
a deck: the most-imported public list that is not native, then the next
older precon. The target is unchanged: any public Moxfield link a player
pastes imports with a simplified count of zero, and keeps doing so as sets
are released. A set release is a manifest refresh, which makes the new
precons the next batches before players meet the cards; the gap report
after each release is the list of mechanics the set introduced.

**What the catalog runs into, in the order it will be met:**

1. **The validator.** Every new op adds a branch to `_validate_effect`, which
   is already the largest function in the tree (`OF-01` in
   [TECH_DEBT.md](../../TECH_DEBT.md)). A per-op validator registry,
   mirroring the engine's `@register`, is the precondition for the long tail.
2. **The deliberate simplifications** in
   [rules-coverage.md](../rules-coverage.md#simplified): layers-lite
   ([ADR 0001](../adr/0001-layers-lite.md)) once two statics genuinely depend
   on each other, card-level targets chosen before modes, and the absence of
   a general replacement system. Each of these is an ADR amendment, not a
   card.
3. **The not-implemented list** in the same page: each is additive and each
   is ordered by how many cards the gap report says it blocks.
4. **Test cost.** `test_every_card_works` and the auto-card gates run over
   the whole pool on every run; at the catalog's size the python slice needs
   sharding by card file, and the golden pool hash a per-file variant.
5. **Art.** Every supported card wants its illustration, which is the art
   store.

This item is continuous: `/extend-roadmap` takes one precon of it and
leaves the item on the page.

## Gate

Per batch: `tests/cards/test_precon_imports.py` over the new deck; one unit
test per capability under `tests/unit/`; the manifest test (every row inside
the window, every `precon` deck has a row) and the coming-soon test
(`tests/server/test_upcoming_precons.py`) still green; and the sampled
whole-game test able to draw the new deck. Across batches,
`author_cards.py --report` for coverage and the generated
[unsupported-cards.md](../unsupported-cards.md) for what blocks what.
