---
id: archidekt-import
title: Archidekt import
area: play
effort: S
impact: low
why: the second link players paste; the maintainer pastes the first
depends_on: []
status: proposed
---

## Today

Only a Moxfield link imports. [deck-import.md](../deck-import.md) already
says a second site is an adapter, not a second card pipeline: what a card
*is* comes from the catalog, and the source supplies only names, quantities
and printings.

## The change

An Archidekt adapter beside `moxfield.py` with the same signature, the URL
parser deciding which one a pasted link goes to, and the same error codes.
Printings are carried through where the source names them, as the Moxfield
adapter does.

## Gate

A test with a real, trimmed Archidekt payload beside `moxfield_deck.json`,
run through `importer.import_deck` as a dry run, asserting the same cards
resolve the same way as the equivalent Moxfield list.
