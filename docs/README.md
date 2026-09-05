# Documentation

| Page | Read it for |
|---|---|
| [architecture.md](architecture.md) | The shape of the system and why there is exactly one seam |
| [engine-rules.md](engine-rules.md) | Turn structure, priority, the stack, combat, state-based actions |
| [rules-coverage.md](rules-coverage.md) | **What is implemented, simplified, and absent** |
| [card-dsl.md](card-dsl.md) | How to write or read a card definition |
| [keywords.md](keywords.md) | Every Magic keyword, which mechanism carries it, and what is still missing |
| [decks.md](decks.md) | The two decks and every substitution made |
| [ai-training.md](ai-training.md) | The environment, action space, agents, self-play |
| [api.md](api.md) | The HTTP surface |
| [frontend.md](frontend.md) | The playtest client |
| [testing.md](testing.md) | Every gate, and the current measured results |
| [design-record.md](design-record.md) | What the design rounds established, and the fidelity findings still open |
| [spec.md](spec.md) | The original brief |
| [playtest-feedback-01.md](playtest-feedback-01.md) | Cycle 1 playtest: findings, all now addressed |
| [playtest-feedback-02.md](playtest-feedback-02.md) | **Cycle 2 playtest: what shipped, and the cycle-3 backlog** |

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

## If you are here to...

**understand the engine** — [architecture.md](architecture.md), then
[engine-rules.md](engine-rules.md).

**find out whether your card would work** — [rules-coverage.md](rules-coverage.md),
then [card-dsl.md](card-dsl.md).

**train something** — [ai-training.md](ai-training.md).

**build a different client** — [api.md](api.md). The engine speaks in legal actions
with opaque ids; a client needs no rules knowledge at all.
