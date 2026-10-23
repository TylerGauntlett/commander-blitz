# Documentation

These pages describe patterns and intent, so that a human or an agent can
understand how the code base is organised and why. They carry no counts, dates
or measured results; what changes with every pull request lives in the code and
its tests. [../AGENTS.md](../AGENTS.md) is the short version for anyone working
here.

| Page | Read it for |
|---|---|
| [architecture.md](architecture.md) | The shape of the system, why there is exactly one seam, and the engine's module map |
| [engine-rules.md](engine-rules.md) | Turn structure, priority, the stack, combat, state-based actions |
| [rules-coverage.md](rules-coverage.md) | **What is implemented, simplified, and absent** |
| [card-dsl.md](card-dsl.md) | The card DSL's concepts: how to read or write a card definition |
| [card-dsl-cookbook.md](card-dsl-cookbook.md) | Worked mechanics: a printed sentence, the JSON that implements it, the near miss |
| [card-dsl-reference.md](card-dsl-reference.md) | The vocabulary tables, generated from the engine and held by a test |
| [card-authoring.md](card-authoring.md) | The pipeline that turns oracle text into a card that passes six gates |
| [card-catalog.md](card-catalog.md) | The Scryfall-derived catalog, art resolution and printings |
| [unsupported-cards.md](unsupported-cards.md) | The mechanics the DSL cannot express yet, generated from the gap records |
| [keywords.md](keywords.md) | Every Magic keyword and which mechanism carries it, held to the engine by a test |
| [decks.md](decks.md) | How a shipped deck describes itself, the test fixtures, and promoting an import |
| [deck-import.md](deck-import.md) | Importing a Moxfield list, what a proxy simplifies, and the two-layer registry |
| [cpus/](cpus/README.md) | **How each CPU deck plays and wins**, and the strategy layer that pilots it |
| [ai-training.md](ai-training.md) | The environment, action space, agents, self-play |
| [api.md](api.md) | The HTTP contract |
| [server.md](server.md) | How the server is organised: the app, the lobby, sessions, art, the desktop mode |
| [client.md](client.md) | How the game client is organised: folders, state, layout modes, input, motion |
| [steamdeck.md](steamdeck.md) | **Playing on a Steam Deck**: the one-line install, offline and online, updates, the controller |
| [../desktop/README.md](../desktop/README.md) | The Electron shell for developers: the sidecar, the content swap, the updaters |
| [testing.md](testing.md) | The quality strategy: which suite owns which question, and why each gate exists |
| [ci-cd.md](ci-cd.md) | What runs where: the gate, what ships, how the site deploys and the Deck releases |
| [deployment.md](deployment.md) | Operating the site: self-hosting, provisioning, rollback, HTTPS |
| [scripts.md](scripts.md) | Every script, and every environment variable the code reads |
| [../data/README.md](../data/README.md) | The data directory: what is authored, what is generated, what is pinned |
| [../TECH_DEBT.md](../TECH_DEBT.md) | The open items, each with what fixing it looks like |
| [roadmap.md](roadmap.md) | **What comes after the core loop**: the feature backlog, generated from the items in `roadmap/`, ranked by impact, effort and what each unblocks |

Decisions with consequences big enough to be worth arguing with are recorded
separately:

- [adr/0001-layers-lite.md](adr/0001-layers-lite.md) — fixed-order continuous effects
- [adr/0002-flat-action-space.md](adr/0002-flat-action-space.md) — a structured index instead of "the nth legal action"
- [adr/0003-auto-mana-payment.md](adr/0003-auto-mana-payment.md) — the engine taps your lands for you
- [adr/0004-incremental-combat.md](adr/0004-incremental-combat.md) — declaring attackers one at a time
- [adr/0005-no-state-cloning.md](adr/0005-no-state-cloning.md) — replay instead of snapshots
- [adr/0006-no-colour-accessibility-requirement.md](adr/0006-no-colour-accessibility-requirement.md) — colour accessibility is out of scope
- [adr/0007-versioned-long-polling.md](adr/0007-versioned-long-polling.md) — how multiplayer clients hear about each other, without sockets
- [adr/0008-url-routing.md](adr/0008-url-routing.md) — real addresses for pods, games and decks
- [adr/0009-offline-first-desktop.md](adr/0009-offline-first-desktop.md) — the Steam Deck build runs its own server and never restarts itself to update
- [adr/0010-release-every-main-build.md](adr/0010-release-every-main-build.md) — every merge that ships is a Steam Deck release, and the PR title's type decides
- [adr/0011-the-card-is-the-illustration.md](adr/0011-the-card-is-the-illustration.md) — full-bleed art, text on scrims, type never carried by colour
- [adr/0012-art-fetched-once-served-locally.md](adr/0012-art-fetched-once-served-locally.md) — art fetched once, served by this app, never upscaled
- [adr/0013-handheld-floors-are-ci-gates.md](adr/0013-handheld-floors-are-ci-gates.md) — the type, target and card floors are gates, not guidelines
- [adr/0014-measured-numbers-invariant-relationships.md](adr/0014-measured-numbers-invariant-relationships.md) — geometry may move, invariants may not, budgets are ceilings
- [adr/0015-every-legal-action-is-one-control.md](adr/0015-every-legal-action-is-one-control.md) — one control per action id; input selects, it never constructs
- [adr/0016-nothing-changes-size-with-game-state.md](adr/0016-nothing-changes-size-with-game-state.md) — reserve space; a collapsing slot moves the board under the cursor
- [adr/0017-animation-reports-state.md](adr/0017-animation-reports-state.md) — the engine commits first; motion narrates and never lags
- [adr/0018-card-data-checked-against-the-printing.md](adr/0018-card-data-checked-against-the-printing.md) — oracle text is a contract; the loader refuses what it would ignore
- [adr/0019-pod-seats-symmetric-readiness.md](adr/0019-pod-seats-symmetric-readiness.md) — everyone locks in; a CPU differs only by deck
- [adr/0020-convoke-is-one-line.md](adr/0020-convoke-is-one-line.md) — convoke and delve are one cast line; the pick is asked while paying
- [adr/0021-art-store-is-committed.md](adr/0021-art-store-is-committed.md) — the crawled art is committed, written by a bot, and asked before Scryfall
- [adr/0022-deck-imports-through-the-site.md](adr/0022-deck-imports-through-the-site.md) — a Deck imports through the site, and a deck on the device is complete or says so

## If you are here to...

**understand the engine** — [architecture.md](architecture.md), then
[engine-rules.md](engine-rules.md).

**find out whether your card would work** — [rules-coverage.md](rules-coverage.md),
then [card-dsl.md](card-dsl.md) and the [cookbook](card-dsl-cookbook.md).

**add cards or a deck** — [card-authoring.md](card-authoring.md), and the skills
described in [../CONTRIBUTING.md](../CONTRIBUTING.md).

**train something** — [ai-training.md](ai-training.md).

**make a CPU play better** — [cpus/README.md](cpus/README.md), then the page for
the deck.

**change the client** — [client.md](client.md), then the ADRs it cites.

**build a different client** — [api.md](api.md). The engine speaks in legal actions
with opaque ids; a client needs no rules knowledge at all.

**change how it is tested or shipped** — [testing.md](testing.md), then
[ci-cd.md](ci-cd.md).

**run it yourself** — [deployment.md](deployment.md).
