# data/art_store/

The catalog's art, crawled ahead of time so no server waits on Scryfall while a
player does. [ADR 0021](../../docs/adr/0021-art-store-is-committed.md) is the
decision; [docs/card-catalog.md](../../docs/card-catalog.md#the-art-store) is
how it is served.

**Written only by `scripts/backfill_art.py`**, which the scheduled
`art-backfill.yml` workflow runs and commits. Never add or edit a file here by
hand: a changed illustration for a card belongs in `data/art/` through a pin.

```
art_store/
├── <ab>/<scryfall_id>.jpg        the front face of one printing, as Scryfall serves it
├── <ab>/<scryfall_id>_back.jpg   its back face, where it has one
├── _unavailable.json             printings the CDN does not have; never asked again
└── _state.json                   the last crawl: when, how much is wanted, how much is held
```

`<ab>` is the id's first two characters. Served behind `data/art/` and ahead
of the lazy cache (`ArtStore.committed`). The Docker image carries this
directory in a layer of its own; the Steam Deck's content package leaves it
out and asks the site instead. No test reads it, which is what lets the gate
treat a crawl as inert.
