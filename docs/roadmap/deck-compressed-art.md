---
id: deck-compressed-art
title: Compressed art, shipped for offline precon play
area: steamdeck
effort: M
impact: medium
why: every Deck update gets smaller and every precon plays offline from the first launch
depends_on: [art-store, official-precons]
status: proposed
---

## Today

The content package the Deck downloads carries the frozen server,
the built client and the card data as one versioned asset, and the art the
repository commits rides inside it at the size the site serves. Anything
outside the shipped pool is fetched on first sight, or eagerly on import,
and only while online ([steamdeck.md](../steamdeck.md#offline-and-online)). So
the Deck's offline promise is exactly as wide as the art it holds, and
every content update re-downloads illustrations that did not change.

## The change

A second encoding of the art, made for the device, shipped
with the precons, and versioned apart from the code:

- **One encoding per surface.** The Deck's panel is a fixed size and the
  largest card it ever draws is the full-card read, so a modern format at
  that width, and the board width beside it, is a fraction of the site's
  bytes with no visible loss on the panel. The rule of
  [ADR 0012](../adr/0012-art-fetched-once-served-locally.md) holds unchanged:
  nothing is ever upscaled, which is exactly why the encoding is sized to
  the largest the Deck draws and not smaller.
- **The art store makes it.** The backfill job writes the device
  encoding beside the full one, keyed the same way, so the site serves
  `/art/...` at either size on request and the sidecar asks for the small
  one. One crawl, two outputs, no second source.
- **The precon window ships inside the package**, so every deck on the
  shelf plays offline with its art on the first launch; everything a player
  imports arrives through the complete-imports item.
- **Art is its own asset.** `content-latest.json` grows an art version, the
  release carries `art-<v>` beside `content-<v>`, and the updater fetches the
  art asset only when its version moved. Code ships on every merge; art
  ships when a set is added to the window or a pin changes. A content update
  gets small enough to take over a hotel connection, which is where a Deck
  usually is.

The licensing ADR the art store forces covers this too: a second encoding
is the same illustration, and the decision is about what is distributed,
not at which size.

## Gate

`e2e/legibility.spec.ts` runs against the compressed set under the handheld
project, so the scrims and the text are proven over the bytes the device
will actually show. The package and the art asset each get a ceiling in the
release workflow, in the spirit of
[ADR 0013](../adr/0013-handheld-floors-are-ci-gates.md): a precon set that
would push the asset over its budget fails the release rather than quietly
doubling every Deck's download. The desktop updater's unit tests cover an
art version that moved and one that did not.
