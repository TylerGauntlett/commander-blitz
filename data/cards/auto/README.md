# Machine-authored cards

Cards written by `commanderblitz.cards.authoring` rather than by hand. They are
**committed and first-class**: loaded by `default_registry()`, playable by the
server, the trainer and the arena.

The gates below now run over `data/cards/` too — see
`tests/cards/test_hand_written_cards.py`. That is new, and it was the wrong way
round for a long time: the machine-written cards were the *only* ones anything
checked, because a hand-written card's `oracle_text` was a summary of its own
implementation and gate 3 had nothing independent to compare against.

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
| registry | the whole pool still loads, and it does not shadow a hand-written card unless `--collect --supersede` says it is replacing one |
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

## There is no promoting one to hand-written

A card does not leave this directory for `data/cards/`. `/author-cards` never
hand-edits `data/cards/`, and the hand-written pool is moving the other way: the
precons and staples there are the cards that predate the pipeline. A card that
needs nuance the pipeline cannot express is a gap in the DSL. File it, build the
capability with `/extend-dsl`, and fix the card where it is.

`--collect` deletes a card's answer once it is collected, so this directory is
the card's only source of truth. A fix made here is not reverted by the next
collect, and `test_auto_cards.py` re-runs all six gates over it.
