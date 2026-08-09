# Generated cards and imported decks

Nothing in here is committed, and nothing in here is hand-written. It is all
reproducible from a Moxfield deck URL, and deleting the whole directory costs
you nothing but a re-import.

```
cards/pool.cards.json      every generated card, one shared pool
cards/pool.images.json     {card_id: {scryfall_id, artist} | null}
cards/pool.coverage.json   {card_id: {coverage, notes[]}}
decks/mox_<publicId>.deck.json
```

## Why one pool and not one file per deck

Two decks that both contain Lightning Bolt would each generate `lightning_bolt`,
and `CardRegistry.from_paths` raises `duplicate card id`. So the cards are a set,
the decks reference them by id, and deleting a deck deliberately leaves its cards
behind — they cost a few KB and the next import probably wants them.

## Why these cards are not in `data/cards/`

`data/cards/` is the **authored** layer: cards somebody wrote rules for, each
covered by `tests/cards/test_every_card_works.py`. A generated card has correct
name, art, cost, types, P/T and keywords, and its non-keyword rules text does
nothing at all. Mixing the two would make the test suite's answer depend on what
was imported last week — see `.gitignore` here for the full argument.

The server loads both layers (`server_registry()`); everything else — tests, the
trainer, the arena — loads only the authored one (`default_registry()`).

## Promoting a generated card

A generated card is written in exactly the `data/cards/*.cards.json` format, so
promotion is a copy: move the object into an authored file, fill in its
`abilities` and `spell_effects` by hand, and delete it from the pool. It is then
a first-class card with tests, and every deck referencing that id picks up the
real rules on the next import.
