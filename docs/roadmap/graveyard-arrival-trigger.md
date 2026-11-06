---
id: graveyard-arrival-trigger
title: A trigger for cards put into a graveyard
area: cards
effort: M
impact: medium
why: every 'whenever one or more cards are put into your graveyard from your library, or from anywhere' card waits on it, The Gitrog Monster and Sidisi among them
depends_on: []
status: proposed
---

## Today

`triggers.TRIGGER_EVENTS` has no event for a card arriving in a graveyard.
`dies` sees creatures from the battlefield, `discard` sees the hand, and
`leaves_graveyard` (`EventType.LEAVES_GRAVEYARD`) is the reverse direction.
`EventType.ZONE_CHANGE` records every move but is deliberately kept off the
trigger bus, and `EventType.LEAVES_GRAVEYARD` is the one narrow departure,
fired from `zones.move_object` with the graveyard's owner as `player` and a
`batch` for "one or more". [rules-coverage.md](../rules-coverage.md#not-implemented)
lists "a mill trigger" as not implemented: `EventType.MILL` has no
`TRIGGER_EVENTS` name.

So no card can say "whenever one or more creature cards are put into your
graveyard from your library" or "whenever one or more land cards are put into
your graveyard from anywhere". Colossal Grave-Reaver and Crawling Sensation,
in the Sultai Arisen precon, are the cards that found it; The Gitrog Monster
and Centaur Vinecrasher wait on the same slug,
`put_into_graveyard_from_anywhere`, in `data/authoring/gaps/`.

## The change

1. An event for a card put into a graveyard, fired narrowly from
   `zones.move_object` the way `EventType.LEAVES_GRAVEYARD` is, carrying the
   graveyard's owner as `player`, the zone the card came from, and the
   `batch` of cards moved together.
2. Its `TRIGGER_EVENTS` row, with a filter over the moved cards (types,
   owner) and `from_zones` read for it, so "from your library" and "from
   anywhere" are one trigger with or without the key. `batched` makes "one
   or more" fire once for a single mill of several cards.
3. A binding for the batch, so an effect can reach "one of them" (Colossal
   Grave-Reaver puts one onto the battlefield) and only cards from this
   batch that are still in the graveyard on resolution.
4. "For the first time each turn" (Crawling Sensation) through the existing
   once-per-turn trigger limit, if it already reads the batched event that
   way; otherwise an open question below.
5. Harvest: Colossal Grave-Reaver, Crawling Sensation, The Gitrog Monster,
   Centaur Vinecrasher, then one `/author-cards` wave over the catalog's
   other cards with the sentence.

It does not put `ZONE_CHANGE` on the trigger bus, and it does not cover a
token "put into a graveyard" (it ceases to exist, 704.5d), nor replacements
that keep a card out of the graveyard (Dauthi Voidwalker is its own gap).

## Gate

A unit test under `tests/unit/` for the new trigger: a mill of several
creature cards fires a batched trigger once, a discard does not fire one
narrowed to the library, "from anywhere" fires for a mill, a discard and a
dying creature card, an opponent's graveyard does not fire a `controller:
"you"` trigger, and the "one of them" binding offers only the batch's cards
still in the graveyard. Colossal Grave-Reaver's and Crawling Sensation's six
gates pass, and the generated DSL reference lists the new trigger event.

## Open questions

- **One event or the existing `MILL` event.** Give "put into a graveyard"
  its own event fired from `zones.move_object` for every source zone, or put
  `EventType.MILL` on the bus and add others per source? Recommended: one
  event from `move_object`, because "from anywhere" has to see every source
  and per-source events would each need the same batching.
- **A dying creature card.** Does a creature that dies also fire it, for a
  "from anywhere" trigger? Recommended: yes, the rules say it was put into a
  graveyard from the battlefield (700.4), and `dies` stays the event for
  "whenever a creature dies".
- **Is it an ADR.** Recommended: no; it is a second narrow departure from
  `ZONE_CHANGE` beside `LEAVES_GRAVEYARD`, and the mill line moves from "not
  implemented" to the implemented table in rules-coverage.md.
