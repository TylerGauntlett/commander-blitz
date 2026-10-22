---
id: every-import-native
title: Every import native, every time
area: cards
effort: L
impact: high
why: the difference between a deck and an inert list, for every link ever pasted
depends_on: [art-store]
status: proposed
continuous: true
---

## Today

Every shipped deck is native; everything else imports as a proxy
that keeps its keywords and loses its text ([deck-import.md](../deck-import.md)).
The loop that closes the gap is in place: the template tier, the agent tier
behind six gates, gap records, and `/extend-dsl` to clear them
([card-authoring.md](../card-authoring.md)). The queue is already ordered by what
players have imported and then by EDHREC rank, which is the right order and
stays.

## The change

**The target.** Any public Moxfield link a player pastes imports with a
simplified count of zero, and keeps doing so as sets are released. That is
the whole catalog, with each card carrying its own verified behaviour, not a
working set. Three things make it a target rather than a wish:

- **A card's unit test already exists as a shape.** Gate 5's expectation is
  the per-card test, `test_auto_cards.py` re-runs all six gates over every
  authored card on every run, and `test_every_card_works.py` casts each one
  in a sandbox and checks where it lands. "Every card has unit tests" means
  every card goes through that door and none is promoted around it; the
  per-deck behaviour files stay for what a one-cast sandbox cannot reach.
- **An unattended worker.** The agent tier's packet is a file format
  precisely so that a worker with no repository open can drain the queue
  ([card-authoring.md](../card-authoring.md#driving-it)). Running that worker
  continuously, collecting through the gates and opening the pull request
  itself, is what turns the loop from a session someone drives into a
  pipeline that keeps up with the catalog. Its gaps still go to
  `/extend-dsl`, which stays a person's decision because it changes the
  engine.
- **Set releases are events.** A refresh of the Scryfall bundle on each
  release, a queue refresh over the new rows, and the worker on them before
  players meet the cards. The gap report after each release is the list of
  new mechanics the set introduced, which is the engine roadmap for that
  quarter written by the set itself.

Until the count reaches zero, an import's report and the per-card marker in
the deck list view say exactly which cards are still waiting, and a card
imported by a player goes to the front of the queue as it does now.

**What the catalog runs into, in the order it will be met:**

1. **The validator.** Every new op adds a branch to `_validate_effect`, which
   is already the largest function in the tree (`OF-01` in
   [TECH_DEBT.md](../../TECH_DEBT.md)). A per-op validator registry, mirroring
   the engine's `@register`, is the precondition for the long tail, not a
   nicety.
2. **The deliberate simplifications** in
   [rules-coverage.md](../rules-coverage.md#simplified). Most of the catalog never
   touches them, but the ones that bite as coverage widens are: layers-lite
   ([ADR 0001](../adr/0001-layers-lite.md)) once two statics genuinely depend on
   each other on a board players build; card-level targets chosen before
   modes, which is why modal spells are the oldest open item in the authoring
   doc; and the absence of a general replacement system, which every "instead"
   that is not one of the named hooks runs into. Each of these is an ADR
   amendment, not a card.
3. **The not-implemented list** in the same page: companions, the initiative,
   voting, energy, damage division, redirection. Each is additive and each is
   ordered by how many cards the gap report says it blocks.
4. **Test cost.** `test_every_card_works` and the auto-card gates run over the
   whole pool on every run. At tens of thousands of cards the python slice
   needs sharding by card file, as the e2e slice is sharded today, and the
   golden pool hash needs a per-file variant so a change to one file re-pins
   one hash.
5. **Art.** Every supported card wants its illustration, which is the art
   store.

This item is continuous: `/extend-roadmap` takes one batch of it, in the
queue's order, and leaves the item on the page.

## Gate

`author_cards.py --report` for coverage, the generated
[unsupported-cards.md](../unsupported-cards.md) for what blocks what, one
import pin per shipped deck, and a new one: a sample of public lists
imported as a dry run on a schedule, with the simplified count reported as
the number this item exists to drive to zero.
