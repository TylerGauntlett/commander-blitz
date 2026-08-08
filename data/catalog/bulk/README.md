# Scryfall bulk-data cache

You do not need to put anything here. Just run:

```bash
python scripts/build_card_index.py
```

If this directory is empty it downloads the current **Default Cards** bundle
(~74 MB gzipped) from <https://scryfall.com/docs/api/bulk-data>, caches it here,
rebuilds `../cards.sqlite` and `../registry_images.json`, and fetches any missing
card art into `data/art/`.

| Command | What it does |
|---|---|
| `build_card_index.py` | downloads only if nothing is cached |
| `build_card_index.py --refresh` | always re-pulls, and deletes the superseded bundle |
| `build_card_index.py --no-download` | offline; uses what is cached or fails |
| `build_card_index.py --check` | never downloads; CI gate for "is the index stale" |

The file stays **gzipped** — the parser streams it that way, so there is no
reason to spend 600 MB of disk expanding it.

**Nothing in this directory is committed.** The `.gitignore` here is deliberate.
The built index is what ships.

Full process, including how to check which bundle the committed index came from:
[docs/card-catalog.md](../../../docs/card-catalog.md).
