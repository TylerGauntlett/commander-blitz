---
id: site-decks-follow
title: Site imports follow their owner to the Deck
area: steamdeck
effort: M
impact: medium
why: a deck imported on the site with friends is on the Deck the next time its owner plays alone
depends_on: [deck-complete-imports]
status: proposed
---

## Today

A deck reaches the site from the Deck through the hand-off: the
Online card carries the Moxfield ids of the decks imported at home
(`onlineUrl` in `frontend/src/logic/desktop.ts`) and `HomeRoute`'s hand-off
imports them before showing the door. Nothing goes the other way, which
[ADR 0009](../adr/0009-offline-first-desktop.md) records as a consequence:
a deck imported on the site does not come back. The two ends do not even
agree on who the owner is. A library is a random id each client mints into
its own `localStorage` (`frontend/src/state/library.ts`), and the site's
browser and the Deck's window are two clients with two ids, so the site has
no way to know that a deck its browser library imported belongs to the
player holding a given Deck.

## The change

A deck imported on the site is on its owner's Deck after the
next launch with a connection, complete, through the bundle
[deck-complete-imports](deck-complete-imports.md) builds. That item is a real
dependency: the bundle route, the adopt step and the `complete` verdict are
what this item reuses unchanged.

- **One library across the hand-off.** The Online hand-off carries the
  Deck's library id, and the site's client adopts it for that browser
  session rather than its own, so whatever the player imports there is
  stamped with the Deck's id. A browser with a library of its own keeps it;
  this changes only a window the Deck opened.
- **The Deck asks what it is missing.** A route on the site lists the decks
  a library owns with their Moxfield ids; at launch with a connection, the
  same step that finishes incomplete decks adopts any the Deck lacks, through
  the bundle, before the door.
- It does not merge two libraries that already exist, or add accounts.

## Gate

A server test lists a library's decks on the site and
nobody else's. The desktop entry point's tests import a deck on a stub site
under the Deck's library, relaunch the sidecar, and assert the deck is on
disk and complete. A client test holds that a window opened by the hand-off
adopts the Deck's library id and an ordinary browser keeps its own.
