# ADR 0024 — "Precon" means the product Wizards sold, and an archetype can pilot one

**Status:** accepted

## Context

The shelf's **Precons** segment held a dozen decks, and none of them was a
preconstructed deck. They were Moxfield lists the maintainer likes, promoted
card for card by `scripts/promote_deck.py`, which wrote `source: "precon"` on
every one because that was the only word the deck file had for "ships with the
engine". A player who filtered to precons got somebody's tuned list and no way
to tell.

The word mattered more once the target became the real decks. Wizards
publishes every Commander preconstructed list with its set, release date and
exact printings, and MTGJSON carries them as data: a rolling five years of
releases is on the order of a hundred decks. Each shipped deck had cost a
strategy module and a page under `docs/cpus/`, required by
`tests/ai/strategy/test_registry.py`. At a hundred decks that rule stops being
a quality bar and becomes a reason not to ship.

## Decision

**`source` has three values, and each is a promise.**

- `precon`: a list Wizards sold as a Commander preconstructed deck, card for
  card, inside the window `scripts/sync_precons.py` names as one constant. Every
  such deck has a row in `data/decks/sources.json`, which the script writes from
  MTGJSON, and carries its `release` (set code, set name, date). A deck that
  ages out of the window leaves the segment.
- `favorite`: a list the maintainer chose to ship. It keeps everything a shipped
  deck has had: native cards, an editorial dossier, a strategy module and a page.
  Promotion through `promote_deck.py` writes this value.
- `moxfield`: a player's import, unchanged.

The shelf's segments are named for them: **Precons**, **Favorites**, **Yours**.

**The Precons segment shows the whole window.** A precon whose cards are not all
native is a **coming-soon shell**: its product name, its release group and a
grayed-out image of its commander, served by printing from the manifest. A shell
is not a deck and not a control: nothing about it can be picked, seated or
played, so [ADR 0015](0015-every-legal-action-is-one-control.md) is untouched.
`GET /api/precons/upcoming` lists the manifest rows that do not ship, by
subtraction, so a precon stops being a shell the moment its deck file loads.

**An archetype is enough to pilot a deck.** A deck file may name an `archetype`,
one of the keys of `ARCHETYPES` in `commanderblitz.ai.strategy.archetypes`, and
`strategy_for` looks the deck up by id, then by commander, then by archetype,
then falls back to the default. The registry test asks every shipped deck for a
module of its own or an archetype. A module and a page are written for a precon
only where the archetype visibly misplays it.

## Consequences

- **Writing `precon` on a deck that is not a Wizards list** breaks the
  segment's promise without failing anything that checks behaviour. The manifest
  test fails instead: every `precon` deck must have a row in `sources.json`, and
  every row must be inside the window.
- **Requiring a module per deck again** would cap the precon shelf at the rate
  somebody can write strategy modules. The registry test is the place that rule
  would come back; it accepts an archetype on purpose.
- A precon's id is its set code and product name (`fdc_calling_all_angels`),
  never its commander's, because the same commander can head a favorite and a
  precon, and a precon can be reprinted in a later product.
- Commander matching still runs before the archetype, so a precon whose
  commander also heads a favorite is piloted by the favorite's plan. A plan's
  key cards that the precon does not run cost nothing; a plan that misplays the
  precon is the signal to give that precon its own module.
- The whole-game test runs a seeded sample of the shipped decks per run. The
  full matrix belongs to the arena, which has its own runner.
- **Filling a shell with substitutions** to make it playable sooner would ship
  a list Wizards did not sell under the word that promises one. A shell waits
  for its cards instead.

## Rejected

- **Keeping the twelve under `precon` and adding the real decks beside them.**
  The segment would mean two things, and the larger it grew the less a player
  could rely on either.
- **Scraping Moxfield's precon section.** Its API refuses unauthenticated
  scripts, and MTGJSON is published as data with the printings attached.
- **Generating a strategy module per precon.** A generated module is an
  archetype with a deck id on it, and it would need a page that says nothing.
