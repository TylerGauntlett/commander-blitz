# Fixture decks

The first Edgar and Aesi lists, retired from the catalogue when the Moxfield
lists replaced them (`../edgar_markov.deck.json`, `../aesi_tyrant_of_gyre_strait.deck.json`).

Hundreds of seeded Python and Playwright tests were written against these exact
99s, so they live on as fixtures:

- `default_registry()` (tests, arena, trainer) always loads them.
- The server loads them only with `COMMANDERBLITZ_FIXTURE_DECKS=1`, which the
  Playwright web server and `scripts/verify.py` set. A player never sees them.
- `seating.json` pins the order a lobby hands decks to CPUs, so a seeded pod
  deals the same opponents it always did.

See [docs/decks.md](../../../docs/decks.md#test-fixtures).
