# ADR 0022 — A Deck imports through the site, and a deck on the device is complete or says so

**Status:** accepted

[ADR 0009](0009-offline-first-desktop.md) made the Steam Deck build a server of
its own that plays offline, and gave it eager art so that a deck imported while
online would still have its illustrations the next time it was not.
[ADR 0021](0021-art-store-is-committed.md) put the site's crawled art store in
front of Scryfall for that fetch. This ADR decides where a Deck's import comes
from and what "imported" promises.

## Context

A Deck import read the list off Moxfield itself, reconciled it against the
Deck's own card pool and catalog, and prefetched the art. Three things were
wrong with that, none of them visible:

- The rules an imported card got were whatever the Deck's content version could
  say. The site deploys on every merge and the Deck catches up at its next
  launch with a connection, so a card authored since then came in as a proxy on
  the Deck while it played with its rules on the site.
- The prefetch returned a count and wrote nothing. An import interrupted
  halfway, by sleep, a dropped network or Steam closing the app, left a deck
  that dealt with blank plates the next time the Deck was offline, and nothing
  on the screen or on disk said so.
- Every Deck spoke to Moxfield directly, which is one more third party whose
  answers the site and the Deck could disagree on.

## Decision

**The Deck asks the site first.** The sidecar posts the Moxfield link to the
hosted import route under its own library id, then fetches
`GET /api/decks/{deck_id}/bundle`: the deck file the site wrote, with its
printings, and the definition of every card it names, with the faces and tokens
those reach. The Deck adopts it card by card (`commanderblitz.cards.bundle`):

- a card the Deck's authored layer already has is the Deck's own;
- a definition the Deck lacks is taken as data. The site's hand-written cards
  go to `generated/cards/site.cards.json`, its proxies to the ordinary pool. The
  authored layer still wins at load (`CardRegistry.extended_with`), so the next
  content update replaces a site copy with the shipped card and nothing moves;
- a definition the Deck's loader refuses, because the site's vocabulary is newer
  than the Deck's engine, becomes a proxy built from the Deck's own catalog, with
  a note saying the rules arrive with the next update.

**Moxfield stays behind the site.** A transport error or a server error from
the site falls back to the old path, Moxfield read by the sidecar. A refusal
the site answers with a code (a private deck, a missing one, an illegal list) is
final, because Moxfield gave the site that answer and would give it again.

**A deck on the device is complete or says so.** An imported deck's file
carries `complete`: written `false` before any art is fetched and `true` once
every illustration the deck can have is on disk. A card with no printing anywhere
has nothing to fetch and does not hold a deck back. A deck file without the field
was imported before this ADR and is treated as unknown, which is checked once and
then recorded. `POST /api/decks/complete` finishes every deck that is not
complete; the desktop door calls it before it draws whenever the site is
reachable. The art store skips what is on disk, so a retry fetches only what
is missing, and a launch with every deck complete fetches nothing.

## Consequences

- An import done through the site writes the deck there too, under the Deck's
  library id. The site's rule for two importers of one list applies: the last one
  owns it. That is the half of [site-decks-follow](../roadmap/site-decks-follow.md)
  that this change does; the other half, the Deck learning about decks first
  imported on the site, is that item's.
- A card authored on the site reaches a Deck before the Deck's content update
  does. It is compiled by the Deck's own loader before it is written, so a
  definition the Deck cannot run never reaches a file the next boot would fail on.
- **Writing the deck file before its cards** would let a boot fail on an id no
  pool defines; the adopt step keeps the importer's order, cards first.
- **Marking a deck complete before its art is on disk, or treating a fetch that
  failed as a card with no art,** reverses the promise silently: the tile says
  nothing and the deck plays grey offline. `ArtStore.missing` is the one place
  that tells the two apart.
- The hosted server never sets `complete`; nothing there reads it.

## Rejected

- **Moxfield only through the site.** Simplest, and one party fewer, but a site
  outage would stop a Deck from importing a deck Moxfield would happily have
  served. The site is a better source, not the only one.
- **The bundle in the import response.** One round trip fewer, but the import
  route's answer is a report for a screen, the bundle is a file for a machine,
  and a route of its own is what the site-to-Deck item fetches later without an
  import.
- **Finishing incomplete decks at boot, before READY.** It would put the network
  in front of every launch, which ADR 0009 rules out: an offline launch is the
  normal launch. The door waits on it only when the site already answered.
- **A Deck that fetches art from the site only.** ADR 0021 rejected it, and
  nothing here changes the reason.
