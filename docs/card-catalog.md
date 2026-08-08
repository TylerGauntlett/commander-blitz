# The card catalog and card art

Cards have art. The bytes are **ours**: they are downloaded once at build time
and served by this application, so a game renders with the network unplugged and
nothing on the board depends on a third party being up.

This page is the whole loop — where the data comes from, how to refresh it, and
how to tell whether what you have is stale.

## Refreshing, in one command

```bash
python scripts/build_card_index.py
```

With nothing cached, that downloads the current Scryfall bundle, rebuilds the
index, and fetches any card art that is missing. It is safe to re-run; a second
run downloads nothing.

| Command | What it does |
|---|---|
| `build_card_index.py` | downloads only if no bundle is cached |
| `build_card_index.py --refresh` | always re-pulls, and deletes the superseded bundle |
| `build_card_index.py --no-download` | offline: uses what is cached, or fails |
| `build_card_index.py --no-art` | rebuild the index, skip the image fetch |
| `build_card_index.py --check` | never downloads; the CI gate for "is the index stale" |
| `fetch_card_art.py` | just the images (`--only`, `--force`, `--dry-run`) |

## What lives where

```
data/catalog/
├── bulk/                        the Scryfall dump. NEVER committed.
│   ├── .gitignore                 ← the only thing between a refresh and a huge commit
│   └── default_cards-*.jsonl.gz   ~74 MB, a download cache
├── cards.sqlite                 the built index          (committed, ~7 MB)
└── registry_images.json         the engine's cards only  (committed, ~20 KB)
data/art/{card_id}.jpg           owned image bytes        (committed, ~9 MB)
```

**Two index artifacts, and the split matters.** `cards.sqlite` holds all ~32,700
distinct English cards and is opened lazily, only by `/api/catalog`. Loading
32k rows at import time would tax `scripts/train.py` and `run_arena.py` for a
thing neither of them uses. `registry_images.json` holds only the ~149 cards the
engine actually ships, and is what the server reads at boot.

**The bundle stays gzipped.** `gzip` streams line by line perfectly well, so
there is no reason to spend 600 MB of disk expanding it.

## Which bundle am I on?

```bash
curl -s localhost:8000/health | python -m json.tool
```

```json
"catalog": {
  "source_name": "default_cards-2026-08-07.jsonl.gz",
  "built_at": "2026-08-08T04:27:49+00:00",
  "rows": 32749
},
"art": { "cached": 144, "known": 149, "artless": 5 }
```

The `meta` table in the index records this at build time, so "where did this art
come from" is answerable in one request rather than by guessing.

## Why `default_cards`

Scryfall publishes several bundles. `default_cards` is every card in English,
one row per printing — **~74 MB gzipped**. `all_cards` is the same thing in every
language at ~372 MB, and every extra row is a non-English printing this build
discards, so it is five times the download for nothing. Verified: the index
built from `default_cards` is byte-identical to one built from the full dump.

Override with `--bulk-type` if you need something else.

## How a card finds its art

`scripts/build_card_index.py` reduces every printing to one row per name:

- **Filtered out**: non-English, digital-only, oversized, `art_series` (2,650 of
  those wear a real card's name while showing a different illustration), and
  memorabilia/joke sets.
- **Deduped** by a *total* order — best scan, then highres, then not-promo, then
  not-textless, then newest, then set, then id. The last key is what makes two
  builds of the same bundle byte-identical, so a refresh commit shows what
  actually changed instead of noise.
- **Image URLs are never stored.** Every Scryfall image URL is a pure function of
  the card's 36-character id, so the index stores the id and derives the rest.
  Storing both sizes verbatim would add ~6.7 MB of pure redundancy.

Then each engine card is matched to a printing (`src/automtg/cards/images.py`):

1. exact name;
2. **for tokens, the sorted subtypes** — Scryfall names the token `"Vampire"`,
   the engine names it `"Vampire Lifelink Token"`. Stripping the `" Token"`
   suffix gives `"Vampire Lifelink"`, which has no printing at all, so that card
   would silently fall back to a blank plate forever. The subtype rule is what
   catches it, and `tests/cards/test_image_resolution.py` pins the regression.
3. the suffix strip, as a second chance;
4. nothing — the client draws a deliberate "no art" plate.

**144 of 149 resolve.** The five that do not are original designs with no
printing anywhere (`aetherling_serpent`, `hydra_broodmaster`,
`kiora_growth_surge`, `kraken_hatchling_swarm`, `overrun_lite`). That set is
frozen in the tests: a *sixth* card appearing in it means a real card stopped
resolving, which is a bug rather than a new custom card.

## Serving

`GET /art/{card_id}.jpg` is a FastAPI route returning `FileResponse`, not a
`StaticFiles` mount — the route also does a **lazy fill**. A card outside
`data/cards/` (a catalog search result, a future deck) has no file yet, so the
first request fetches it once, writes it beside the others, and serves it. The
app gets more self-owned as it is used, and the browser still only ever talks to
this server.

`GET /api/images` hands the client every card's art path in one cacheable
response. It carries **no `cards.scryfall.io` URL** — `tests/server/test_art_api.py`
asserts the string never appears in the payload, because that is the whole point.

The image deliberately does *not* ride along on `card_view`. `player_view`
re-serialises ~90 cards on every poll of the AI pump, and the image is a function
of the immutable `card_id`, so putting it there would re-send a constant
thousands of times a game.

## If you are working offline

Everything except the refresh works. The index and the art are committed, so a
fresh clone plays with full art and never touches the network. `--check` never
downloads either, and exits 0 with a printed `SKIP:` when no bundle is cached —
which is every machine that has not refreshed recently.

If the artifacts are missing entirely, the app still boots and deals a game: it
renders text frames, `/api/images` reports every card as artless, and
`/api/catalog` returns 503. That path has a test
(`TestDegradesWithoutTheArtifacts`).

## A note on the images

`data/art/` is Wizards-owned illustration, cached from a third-party CDN for a
local playtest client. That is normal for this kind of tool, but it is worth a
deliberate decision before this repository is made public.
