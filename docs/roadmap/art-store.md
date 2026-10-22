---
id: art-store
title: An art store the servers own
area: cards
effort: M
impact: high
why: removes the one runtime dependency on a third party, and every deck and card expansion sits on top of it
depends_on: []
status: proposed
adr: true
---

## Today

The repository commits the art for the cards it ships, and the
hosted server lazily fetches anything else from Scryfall the first time a
board shows it ([card-catalog.md](../card-catalog.md#serving)). The browser
never talks to Scryfall, which is the rule
[ADR 0012](../adr/0012-art-fetched-once-served-locally.md) set; the server
still does, at a moment a player is waiting, and so does every Steam Deck
on its own behalf. At catalog scale that is a rate limit and an outage
waiting to be met by whoever imports the wrong deck on the wrong evening.

## The change

Download every illustration once, slowly, into a store the
project owns, and have every Commander Blitz server serve from that store
and nothing else:

- **A backfill job** that walks the catalog at the pace Scryfall asks for,
  resumable, keyed by `scryfall_id`, and idempotent, so it can be stopped
  and restarted and never fetches a file twice. It runs on a schedule after
  each bundle refresh to pick up new printings. One printing per name is the
  first pass, since that is what the index already resolves; the printings
  decks have chosen and the pins come next; every printing is a later,
  separate decision, because it is an order of magnitude more storage for
  illustrations almost nobody will see.
- **The store** is a volume or an object store, not the repository, since a
  git history of every illustration ever printed is the wrong shape. The
  serving path is unchanged: `/art/{card_id}.jpg` and `?p=` keep their
  meaning and the owned-wins rule keeps its order, with the store as a third
  layer behind the committed files and ahead of the lazy fill. The lazy fill
  stays as the fallback for a printing the backfill has not reached, and the
  `_missing` set stays as the answer for one Scryfall does not have.
- **The Deck fetches from the site**, not from Scryfall. The sidecar's lazy
  fill and eager prefetch point at the hosted origin's `/art`, so one
  throttled crawl serves every device and the desktop's offline story is
  unchanged: what it has, it has.
- **`/health` reports the backfill**: how far it is, when it last ran, and
  how many lookups fell through to the fallback, which is the number that
  should go to zero and stay there.

**The decision this forces.** `data/art/` is Wizards-owned illustration, and
[card-catalog.md](../card-catalog.md#a-note-on-the-images) asks for a
deliberate decision before the corpus grows. A store holding the whole
catalog is that moment, and the decision belongs in an ADR before the
backfill runs: what is stored, at what size, under which policy, and what
the content package the Deck downloads carries versus fetches.

## Gate

The art API tests gain the third layer: a store file is served ahead of a
cached one and behind a committed one, and a request for a printing the
store lacks still fills lazily. The backfill script is resumable under test:
interrupt it, run it again, and no file is fetched twice. `/health` carries
the backfill fields and `tests/server/test_art_api.py` asserts the payload
still names no `cards.scryfall.io` URL.
