---
id: deck-list-view
title: Viewing a deck's list
area: decks
effort: M
impact: medium
why: every deck pick, and the only honest per-card view of an import
depends_on: []
status: proposed
---

## Today

The dossier shows the commander, the editorial half, the curve, the
land count and the simplified count. It never shows the list, so the only
way to know what is in a deck is to deal it, and the only way to know
*which* of an import's cards are inert is the import report at the moment
of import.

## The change

A list view, the way Moxfield's default view reads: every card as a
face, grouped by type with the group counts, sorted by mana value within a
group, with `Y` or hover reading the card in full through the same preview
the board uses. Specifics:

- A new `GET /api/decks/{id}/cards` rather than widening `DeckDetail`, which
  is fetched for every dossier and should stay light; the list is derived at
  request time like the curve, so it cannot drift from the file.
- A **per-card** simplified marker, so an imported deck says which cards are
  inert rather than only how many; the coverage file the importer writes
  already knows.
- Where the source list carries the author's categories, keep them on the
  import and offer "by category" beside "by type"; where it does not, "by
  type" is the only grouping and nothing is invented.
- A stats strip: the curve that exists, colour pips against mana sources,
  type counts, and the bracket signals once brackets exist. Charts
  follow the dataviz rules the project already uses for the curve, in both
  themes.
- `StaticCard` for every face, since a second `layoutId` for an oid would
  animate between copies, and group headers as regions so the ring walks a
  hundred cards by group rather than one at a time.

The same view is what a seat opens in the pod to check an opponent's locked
deck, so it has to render for a deck with no dossier at all. It is worth
more once the precons exist, but nothing in it waits on them.

## Gate

A server test that the new route's groups sum to the deck's card count and
its per-card markers agree with the coverage file; a story per layout mode
with a hundred faces under the floors; and an e2e spec that walks the list
with a pad by group and reads one card.
