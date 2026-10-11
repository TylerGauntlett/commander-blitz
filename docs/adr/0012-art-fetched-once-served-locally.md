# ADR 0012 — Art is fetched once, served locally, never upscaled

**Status:** accepted

[ADR 0009](0009-offline-first-desktop.md) covers the desktop shell's eager prefetch
only. This ADR is the pipeline it prefetches from.

## Context

Once [ADR 0011](0011-the-card-is-the-illustration.md) made the illustration the
card, the client needed an illustration for every card, on every surface, with
no network at render time — the board is tested with the network unplugged and
the desktop build plays offline.

The first proposal routed through Moxfield. Tested leg by leg: its search
answers a scripted client with a Cloudflare refusal, and its asset host serves
the whole card rather than the art, and only by an id the refused search
returns. Scryfall's named-card endpoint is open and keyless and returns an
`art_crop`. The architecture survived the swap; only the lookup changed.

The second finding was about size. Every Scryfall image variant was measured.
`art_crop` is the art alone, and it is small; the larger variants are whole-card
scans whose art band is no bigger. There is no source of more pixels. Any panel
that draws the crop larger than it is draws blur.

## Decision

**Fetch each image once, keep it, serve it from this application, and never
draw it above its native size.**

- **Card art** is fetched at build time by `scripts/fetch_card_art.py` — fetch
  once, store in the repo, skip what is already present (`--force` and `--only`
  are the only ways past that) — and at runtime lazily by `ArtStore._fill` in
  `src/commanderblitz/server/art.py` for a card the build did not know about (a
  catalogue search result, an import). `GET /art/{card_id}.jpg` is a route that
  does the fill, not a static mount. A committed file always beats a cached one
  of the same name (`ArtStore.path_for`), because the cache is only what some
  earlier boot believed the printing to be.
- **The browser talks only to this server.** `/api/images` hands out this app's
  paths and carries no `cards.scryfall.io` URL; `tests/server/test_art_api.py`
  asserts the string never appears, because that is the whole point. A deck's
  own choice of printing rides as a query on the same route.
- **Symbols take the same path.** `frontend/scripts/fetch-symbols.py` pulls the
  symbols the engine can produce (`WANTED`) into `frontend/public/symbols/`;
  `ManaSymbol` draws them from there. The SVGs ship coloured and are never
  recoloured.
- **The ceiling.** A crop is never rendered much above native. A field bigger
  than that is blurred on purpose and carries no detail, with something crisp on
  top at or below native — the orb's wash, the seat's ground under its veil. A
  window that wants more picture keeps the crop's full width and trims height
  (the handheld reader, the seat's portrait) rather than scaling it. `CardPreview`
  and `doorArt.tsx` carry the number this is measured against.
- **The front door's art is drawn, not fetched.** A front door has no card to be
  a crop of, a vector ground is exact at every stage scale, and it is the only
  asset that needs no server at all.
- **A card with no printing gets the fallback** — the colour-identity gradient
  and `no art` from ADR 0011 — never a broken image. `frontend/src/logic/cardArt.ts`
  tells "not fetched yet" (`undefined`) from "has no printing" (`null`) so the
  first paint does not flash the plate on every card.

## Consequences

- A fresh clone plays with full art and never touches the network. The app gets
  more self-owned as it is used.
- The repository carries Wizards-owned illustration cached from a third-party
  CDN for a local playtest client. `docs/card-catalog.md` has the note.
- **Widening any panel that draws a crop past native reverses this decision**,
  as does adding a runtime image CDN or putting an image URL on `card_view`. The
  first is the easy one to do by accident: a seat panel that scales with the
  viewport will cross the ceiling on a large display without anyone changing a
  line about art. Cap the panel, or blur the field and put something crisp on it.
- Which printing a card shows is decided at build time by the index's dedupe
  sort, overridden by `data/catalog/art_pins.json`, overridden per seat by a
  deck's `printings`. A pin that matches nothing warns rather than failing
  quietly, and a test holds every committed pin to the committed index.

## Rejected

- **The Moxfield route.** Refuses scripted clients and serves whole cards.
- **Hotlinking Scryfall at render time.** Breaks offline play, makes every board
  render a third-party request, and puts a CDN's availability in the frame rate.
- **A larger image variant to buy sharpness.** The larger variants are whole-card
  scans; the illustration inside them is the same size. The pixels do not exist.
- **Upscaling with a soft filter and calling it a style.** One mockup did this
  for its hero panel. It reads as out of focus, and the tint it leaned on was
  already spent saying which card was selected.
