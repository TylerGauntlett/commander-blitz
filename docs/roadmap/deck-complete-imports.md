---
id: deck-complete-imports
title: Imports complete on the device
area: steamdeck
effort: M
impact: high
why: a deck imported on a Deck plays offline later exactly as it played online, which is the whole offline promise for anything not on the shelf
depends_on: []
status: in_progress
adr: true
---

## Today

An import on the Deck fetches the list from Moxfield itself
(`moxfield.load` inside the sidecar's `POST /api/decks/import`), reconciles
it against the sidecar's own catalog (`importer.import_deck`), and with
`COMMANDERBLITZ_EAGER_ART` prefetches every printing the deck names
(`ArtStore.prefetch`, [steamdeck.md](../steamdeck.md#offline-and-online)).
Since [ADR 0021](../adr/0021-art-store-is-committed.md) that prefetch asks
the site's `/art` store first and Scryfall second, so the art half already
goes through the site; the list does not. The response's `art_prefetch` is a
count, and nothing is recorded anywhere: an import interrupted at the
eightieth card is a deck that plays with twenty blank plates the next time
the Deck is offline, and nothing says so. The rules an imported card gets are
whatever the Deck's content version can say, which may be less than the site
says for the same card.

## The change

An import on the Deck asks the site first, and is not done
until it would play the same with the network unplugged. Decided when the
item was taken up: the Scryfall fallback behind the site's store stays
([ADR 0021](../adr/0021-art-store-is-committed.md) rejected a Deck that can
only ask the site); the illustration is the site's `art_crop` as served, and
a device encoding stays with
[deck-compressed-art](deck-compressed-art.md); a Moxfield import still works
when the site does not answer; and a deck imported on the site following its
owner to the Deck is its own item,
[site-decks-follow](site-decks-follow.md).

- **The import goes through the site.** The sidecar sends the Moxfield link
  to the hosted server's import route under its own library id, then asks a
  new route, `GET /api/decks/{deck_id}/bundle`, for the deck file with its
  printings and the definitions of every card it names, with the faces and
  tokens they reach. A card the Deck already has is its own; a definition
  it lacks is taken as data, so a card the site has authored since the
  Deck's last content update arrives with its rules rather than as a proxy.
  A definition the Deck's loader refuses, because its vocabulary is newer
  than the Deck's engine, becomes a local proxy with a note and resolves on
  the next content update, where the authored layer wins over it
  (`CardRegistry.extended_with`).
- **The site not answering is not a failure.** A transport error or a
  server error from the site falls back to today's path, Moxfield read by
  the sidecar itself; a refusal the site gives with a code (a private deck,
  a missing one, an illegal list) is the answer, because Moxfield would give
  the same one.
- **Complete means complete.** The deck file carries `complete`, written
  `false` before the art is fetched and `true` once every illustration the
  deck can have is on disk; a card with no printing anywhere is not
  missing. `art_prefetch` becomes the verdict, with what is still missing.
  A deck that is not complete says so on its tile and in the dossier.
  `POST /api/decks/complete` finishes every incomplete deck, retrying what
  an earlier attempt could not reach, and the desktop door calls it before
  showing itself whenever the site is reachable, the way the hand-off to the
  site imports decks before showing the door today. Nothing on disk is
  fetched twice, and a launch with every deck complete costs nothing.

It deliberately does not change what the site stores, add an encoding, or
make the site's own imports reach the Deck.

## Gate

The desktop entry point's tests run an import against a stub
site, the real hosted app with Moxfield answered from the fixture, with every
other host refused, and assert every file the deck names is on disk and the
deck is marked complete; then interrupt a second import halfway by stopping
the process, relaunch, and assert `POST /api/decks/complete` finishes it
without fetching anything twice. Server tests hold the bundle route, the
fall-back to Moxfield, and a definition the loader refuses becoming a proxy.
The sidecar spec in the e2e matrix imports through the same stub, turns the
stub off, and plays several turns on the imported deck with nothing off the
device; playing a game to its result is `full-game.spec.ts`'s, whose length
the turn cap alone bounds. A story shows an incomplete deck's tile and dossier.
