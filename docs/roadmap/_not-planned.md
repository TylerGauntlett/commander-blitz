## Not planned

Named so that nobody re-litigates them by accident:

- **Colour accessibility** stays out of scope
  ([ADR 0006](../adr/0006-no-colour-accessibility-requirement.md)).
- **A progressive web app** and **WebSockets** were each rejected with
  reasons ([ADR 0009](../adr/0009-offline-first-desktop.md),
  [ADR 0007](../adr/0007-versioned-long-polling.md)); the matchmaking queue
  is the first thing that could revisit the second, and only at a scale the
  site does not yet have.
- **Non-English cards.** The catalog is built from the English bundle on
  purpose ([card-catalog.md](../card-catalog.md#why-default_cards)).
- **Undo in a multiplayer game.** Refused by design
  ([api.md](../api.md#undo)); a take-back by consent is a different feature and
  nobody has asked for it.
