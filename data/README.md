# data/

Everything the engine, the server and the card pipeline read from disk, in one
map. Each directory below says whether it is committed or generated, which test
pins it, and which page owns the details. The per-directory READMEs are linked
rather than repeated.

```
data/
├── cards/            the authored card pool            committed
│   └── auto/         machine-authored cards            committed
├── decks/            the shipped decks and the precon manifest  committed
│   └── fixtures/     retired lists kept for tests      committed
├── catalog/          the Scryfall-derived index        committed, except bulk/
├── art/              owned card art                    committed
├── art_store/        the crawled catalog art           committed, by a bot
├── authoring/        the card pipeline's working state partly committed
└── generated/        imports and runtime writes        gitignored
```

The root resolves through `cards.registry.data_dir()`, which
`COMMANDERBLITZ_DATA_DIR` overrides; `generated/` resolves separately through
`generated_dir()` and `COMMANDERBLITZ_GENERATED_DIR`, so a read-only install can
still write ([docs/scripts.md](../docs/scripts.md#environment-variables)).

## `cards/` — the authored layer

`*.cards.json` files, batched by the deck they were written for plus the shared
staples, basics and tokens. Every file is hand-written in origin, but **the only
one a person edits by hand today is `tokens.cards.json`**: a missing token is a
gap record of `kind: "token"` closed under `/extend-dsl`. Every other card is
repaired through the pipeline (`author_cards.py --collect --supersede`, which
deletes the incumbent here and writes the replacement to `auto/`), and
`audit_cards.py` rewrites only record fields such as the printed `oracle_text`.
See [docs/card-authoring.md](../docs/card-authoring.md#repairing-a-hand-written-card).

A card id is defined once and referenced by any number of decks;
`CardRegistry.from_paths` raises on a duplicate. Test-only cards live in
`tests/data/testing.cards.json` and never reach a real game.

Pinned by `tests/cards/test_every_card_works.py` (every card is cast and
resolved), `tests/cards/test_hand_written_cards.py` (the six authoring gates),
and `tests/cards/test_golden_pool.py`, which hashes the whole compiled pool
against `tests/cards/golden_pool.sha256`.

### `cards/auto/`

Cards written by `commanderblitz.cards.authoring` rather than by hand, committed
and first-class: `templates.cards.json` holds the definitions and
`expectations.json` maps each card id to the observable outcome that was
checked when it was accepted. `tests/cards/test_auto_cards.py` re-runs all six
gates over every card and fails on an expectation whose card is gone. Nothing
moves from here into `cards/`. Read [cards/auto/README.md](cards/auto/README.md).

## `decks/` — the shipped decks

One `*.deck.json` per shipped deck: identity, `source` (`precon` or `favorite`),
editorial fields (`tags`, `ratings`, `strategy`, `signature`), an optional
`archetype`, `release` for a precon, optional `substitutions` and `printings`,
then the list. A favorite is named after its commander; a precon after its set
and product. Every card must be native, which is what `scripts/promote_deck.py`
and `scripts/sync_precons.py --write-deck` enforce when they write one here.
`sources.json` is the precon manifest `sync_precons.py` writes from MTGJSON,
held by `tests/cards/test_precon_sources.py`. Pinned by
`tests/cards/test_deck_legality.py`, `tests/cards/test_deck_metadata.py` and a
`tests/cards/test_<deck>_deck.py` per deck. Owned by
[docs/decks.md](../docs/decks.md).

### `decks/fixtures/`

The retired first Edgar and Aesi lists and `seating.json`, which pins the order
a lobby hands decks to CPUs so a seeded pod deals the same opponents. Loaded by
`default_registry()` always and by the server only under
`COMMANDERBLITZ_FIXTURE_DECKS=1`; a player never sees them.
`tests/server/test_fixture_decks.py` holds both halves. Read
[decks/fixtures/README.md](decks/fixtures/README.md).

## `catalog/` — the Scryfall-derived index

| Path | Committed | What it is |
|---|---|---|
| `cards.sqlite` | yes | One row per distinct English card name with art. Opened by the server at boot (`cards.images.load_index`) for catalog search and deck import, and by the authoring tools; the trainer and the arena never touch it |
| `registry_images.json` | yes | Which printing each card the engine ships draws. Read at server boot |
| `art_pins.json` | yes | Printings chosen by hand where the build's sort picks the wrong picture. Build-time only; nothing at runtime reads it |
| `bulk/` | no | The download cache for the Scryfall dump that the index is built from. Its own `.gitignore` is the only committed thing in it |

All three artifacts are written by `scripts/build_card_index.py`, whose
`--check` is the CI gate for a stale index. Pinned by
`tests/cards/test_card_index.py` and `tests/cards/test_image_resolution.py`,
which asserts the set of cards with no printing anywhere is exactly the known
one. Read [catalog/bulk/README.md](catalog/bulk/README.md); the build, the dedupe
order and the pins are owned by [docs/card-catalog.md](../docs/card-catalog.md).

## `art/` — owned card art

`{card_id}.jpg` per card the engine plays, plus `manifest.json` recording each
file's printing and artist. Committed, baked into the deploy image, and
written only by `scripts/fetch_card_art.py` — never at runtime. A deck's chosen
printing that differs from the one here is crawled into `art_store/`, and
until the crawl reaches it the server fetches it into `generated/art/`. `tests/server/test_art_api.py::TestTheDeployedShape`
pins that the two directories stay apart. Read [art/README.md](art/README.md);
serving and the owned-wins rule are in
[docs/card-catalog.md](../docs/card-catalog.md#serving).

## `art_store/` — the crawled catalog art

`{scryfall_id}.jpg` and `{scryfall_id}_back.jpg` for every printing the index
resolves, every pin and every printing a shipped deck chose, sharded by the
id's first two characters. Committed, but written only by
`scripts/backfill_art.py` through the scheduled `art-backfill.yml` workflow.
Served behind `art/` and ahead of `generated/art/`; in the image, not in the
Deck's content package. Read [art_store/README.md](art_store/README.md) and
[ADR 0021](../docs/adr/0021-art-store-is-committed.md).

## `authoring/` — the card pipeline's working state

| Path | Committed | What it is |
|---|---|---|
| `queue.json` | yes | What is done, what failed and why, most-played first. Written by `scripts/author_cards.py` through `cards.authoring.queue` |
| `gaps/<card_id>.json` | yes | One record per card the DSL could not say: the blocked sentences, what it needs, the closest existing capability. `scripts/report_gaps.py` collapses them into [docs/unsupported-cards.md](../docs/unsupported-cards.md) |
| `packets/` | no (gitignored) | Work packets for an agent worker. `author_cards.py --tier agent` regenerates one on demand |
| `answers/` | transient | A worker's answer per card. `--collect` reads it through `cards.authoring.packet.read_answers` and deletes it once the card ships, so nothing here outlives a collect. `tests/cards/test_authoring_tools.py` exercises the read-and-retire against a scratch directory |

Owned by [docs/card-authoring.md](../docs/card-authoring.md).

## `generated/` — the server-only layer

Nothing here is committed and nothing is hand-written: generated card
definitions and imported decks (`cards/pool.*.json`, `decks/mox_*.deck.json`)
and the lazy art fill (`art/`), all reproducible from a Moxfield URL. Only
`server_registry()` loads it; `default_registry()` — tests, the trainer, the
arena, the CLI — never does, which is what keeps `pytest`'s answer independent
of what somebody imported last week. `tests/cards/test_two_layer_registry.py`
holds the split and `tests/cards/test_generated_dir.py` holds every runtime
write path to `generated_dir()`. On the hosted site this directory is the one
Docker volume that outlives a deploy; on the desktop it is the per-user data
directory. Read [generated/README.md](generated/README.md); the import flow is
owned by [docs/deck-import.md](../docs/deck-import.md) and the volume by
[docs/deployment.md](../docs/deployment.md#things-to-know).
