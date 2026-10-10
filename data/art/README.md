# data/art/

One illustration per card the engine plays, as `{card_id}.jpg` (and
`{card_id}_back.jpg` for a double-faced card), fetched once by
`scripts/fetch_card_art.py` and committed so a game renders with the network
unplugged. `manifest.json` records, for every file, the card it belongs to, the
Scryfall id of the printing and the **artist**.

The images are © Wizards of the Coast and are used as unofficial Fan Content under
the [Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy);
they were obtained through [Scryfall](https://scryfall.com/docs/api). See
[NOTICE.md](../../NOTICE.md). If you are an artist who would like an image
removed, open an issue and it will be taken out.

Art for a deck's *chosen printing* that differs from the one here is not committed:
the server fetches it on demand into `data/generated/art/`, which is gitignored.
