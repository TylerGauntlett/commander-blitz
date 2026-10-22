---
id: deck-complete-imports
title: Imports complete on the device
area: steamdeck
effort: M
impact: high
why: a deck imported on a Deck plays offline later exactly as it played online, which is the whole offline promise for anything not on the shelf
depends_on: []
status: proposed
---

## Today

An import on the Deck fetches the list from Moxfield itself,
reconciles it against the sidecar's own catalog, and with eager art
prefetches every printing from Scryfall ([steamdeck.md](../steamdeck.md#offline-and-online)).
That is two third parties that both have to be up, a rate limit paid per
device, and no record of whether the prefetch finished: an import
interrupted at the eightieth card is a deck that plays with twenty blank
plates the next time the Deck is offline, and nothing says so. The rules an
imported card gets are whatever the Deck's content version can say, which
may be less than the site says for the same card.

## The change

The Deck talks to one origin, and an import is not done
until it would play the same with the network unplugged.

- **The import goes through the site.** The sidecar sends the Moxfield link
  to the hosted server's import route, which does what it does today, and
  asks back for a bundle: the deck file with its printings, and the card
  definitions behind it, so that a card the site has authored since the
  Deck's last content update arrives as data rather than as a proxy. A
  definition the Deck's loader refuses, because its vocabulary is newer than
  the Deck's engine, becomes a proxy with a note, exactly as an unsupported
  card does now, and resolves on the next content update. Moxfield is still
  the source of the list; the Deck simply never speaks to it directly, so
  the site's catalog and the Deck's agree on what every card *is*.
- **Every illustration comes from the site's store**, at the device
  encoding, through the same `/art` path the browser uses, into the Deck's
  own generated directory beside the deck. One throttled crawl on the site
  serves every device, and a printing the backfill has not reached is the
  site's lazy fill to fetch, never the Deck's.
- **Complete means complete.** The import response already carries
  `art_prefetch`; it becomes a verdict rather than a count. A deck whose art
  is all on disk is marked complete in its file and plays offline. One that
  is not says so on its tile and in the dossier, and a resumable job keyed
  by deck finishes it on the next launch with a connection, before the door
  is shown, the way the hand-off to the site imports decks before showing
  the door today. Nothing is ever fetched twice, and a deck already
  complete costs the next launch nothing.
- **The same path, both ways.** A deck imported on the site follows its
  owner to the Deck through the same bundle, which closes the "a deck
  imported on the site does not come back" consequence recorded in
  [ADR 0009](../adr/0009-offline-first-desktop.md). Pods with friends stay on
  the site, as that ADR decided; this item is about what is on the device
  when there is no connection.

## Gate

The desktop entry point's tests run an import against a stub site
with the network otherwise refused, assert every file the deck names is on
disk and the deck is marked complete, then interrupt a second import
halfway, relaunch, and assert it finishes. The sidecar spec in the e2e
matrix plays a full game on the imported deck offline.
