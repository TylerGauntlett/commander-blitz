# Documentation

| Page | Read it for |
|---|---|
| [architecture.md](architecture.md) | The shape of the system and why there is exactly one seam |
| [engine-rules.md](engine-rules.md) | Turn structure, priority, the stack, combat, state-based actions |
| [rules-coverage.md](rules-coverage.md) | **What is implemented, simplified, and absent** |
| [card-dsl.md](card-dsl.md) | How to write or read a card definition |
| [card-authoring.md](card-authoring.md) | The pipeline that turns oracle text into a card that passes six gates |
| [card-catalog.md](card-catalog.md) | The Scryfall-derived catalog, art resolution and printings |
| [unsupported-cards.md](unsupported-cards.md) | The mechanics the DSL cannot express yet, generated from the gap records |
| [dsl-changelog.md](dsl-changelog.md) | How the card DSL got to where it is: what changed, what was fixed, and why |
| [keywords.md](keywords.md) | Every Magic keyword, which mechanism carries it, and what is still missing |
| [decks.md](decks.md) | The twelve shipped decks, the test fixtures, and promoting an import |
| [deck-import.md](deck-import.md) | Importing a Moxfield list, and the two-layer registry that keeps imports out of tests |
| [cpus/](cpus/README.md) | **How each CPU deck plays and wins**, and the strategy layer that pilots it |
| [ai-training.md](ai-training.md) | The environment, action space, agents, self-play |
| [api.md](api.md) | The HTTP surface |
| [frontend.md](frontend.md) | The playtest client |
| [steamdeck.md](steamdeck.md) | **Playing on a Steam Deck**: the one-line install, offline and online, updates, the controller |
| [deployment.md](deployment.md) | How CI, the site and the desktop releases ship, and how to self-host |
| [testing.md](testing.md) | Every gate, and the current measured results |
| [design-record.md](design-record.md) | What the design rounds established |

Decisions with consequences big enough to be worth arguing with are recorded
separately:

- [adr/0001-layers-lite.md](adr/0001-layers-lite.md) — fixed-order continuous effects
- [adr/0002-flat-action-space.md](adr/0002-flat-action-space.md) — a structured index instead of "the nth legal action"
- [adr/0003-auto-mana-payment.md](adr/0003-auto-mana-payment.md) — the engine taps your lands for you
- [adr/0004-incremental-combat.md](adr/0004-incremental-combat.md) — declaring attackers one at a time
- [adr/0005-no-state-cloning.md](adr/0005-no-state-cloning.md) — replay instead of snapshots
- [adr/0006-no-colour-accessibility-requirement.md](adr/0006-no-colour-accessibility-requirement.md) — colour accessibility is out of scope
- [adr/0007-versioned-long-polling.md](adr/0007-versioned-long-polling.md) — how multiplayer clients hear about each other, without sockets
- [adr/0008-url-routing.md](adr/0008-url-routing.md) — real addresses for pods, games and decks, reversing "no router"
- [adr/0009-offline-first-desktop.md](adr/0009-offline-first-desktop.md) — the Steam Deck build runs its own server, goes to the site for friends, and never restarts itself to update
- [adr/0010-release-every-main-build.md](adr/0010-release-every-main-build.md) — every merge that ships is a Steam Deck release, versioned `X.Y.<commits>`, and the PR title's type decides

## If you are here to...

**understand the engine** — [architecture.md](architecture.md), then
[engine-rules.md](engine-rules.md).

**find out whether your card would work** — [rules-coverage.md](rules-coverage.md),
then [card-dsl.md](card-dsl.md).

**add cards or a deck** — [card-authoring.md](card-authoring.md), and the skills
described in [../CONTRIBUTING.md](../CONTRIBUTING.md).

**train something** — [ai-training.md](ai-training.md).

**make a CPU play better** — [cpus/README.md](cpus/README.md), then the page for
the deck.

**build a different client** — [api.md](api.md). The engine speaks in legal actions
with opaque ids; a client needs no rules knowledge at all.

**run it yourself** — [deployment.md](deployment.md).
