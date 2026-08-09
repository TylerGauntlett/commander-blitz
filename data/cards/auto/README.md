# Machine-authored cards

Cards written by `automtg.cards.authoring` rather than by hand. They are
**committed and first-class**: loaded by `default_registry()`, playable by the
server, the trainer and the arena, and covered by the same gates as everything in
`data/cards/`.

They are not the inert proxies in `data/generated/`. A proxy has the right name,
art, cost and keywords with its rules text doing nothing. A card in here has
**demonstrated its behaviour** — nothing is written that has not cleared all six
gates in `authoring/verify.py`:

| | |
|---|---|
| schema | the JSON is a `CardModel` |
| compile | ops, selectors, triggers, keywords, static constraints |
| residual | the printed text is *fully* represented, nothing left over |
| playable | it can be cast in a sandbox and resolves to the right zone |
| behaviour | a **non-empty** expectation that actually holds |
| registry | the whole pool still loads, and it does not shadow a hand-written card |

Gate 5 is the one that matters. `compile_card` validates *vocabulary*, not
*meaning* — a card can say "draw two cards" and gain life instead, and it will
compile, cast and resolve without ever raising. So every card here is paired with
an assertion about the board in `expectations.json`, and the pair is accepted or
rejected together.

## Layout

```
data/cards/auto/
├── *.cards.json      the definitions, batched by how they were written
└── expectations.json card_id -> the observable outcome that was checked
```

## Re-verifying

```bash
pytest tests/cards/test_auto_cards.py -q
```

Runs every gate again over everything committed here. A card that stops passing
is a card that must come out — the whole value of this directory is that its
contents are known to work, not assumed to.

## Promoting one to hand-written

Move the object into a file in `data/cards/`, delete it here, delete its
expectation. It is then an ordinary hand-written card. Do that when a card needs
nuance the pipeline cannot express but a person can.
